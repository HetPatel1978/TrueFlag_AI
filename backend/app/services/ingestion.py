"""Atomic alert/case/audit persistence with durable, concurrency-safe request receipts."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Alert, AlertIngestion, AuditEvent, Case
from app.schemas.alerts import AlertIngestionInput


class IngestionConflict(Exception):
    pass


class IngestionStateError(SQLAlchemyError):
    """Stored business state is incomplete; never silently repair it on retry."""


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def fingerprints(body: AlertIngestionInput) -> tuple[str, str]:
    # Exact rational representation for hashing only: 1/1.0 and signed zero are equivalent.
    # Preserve actual submitted values/types in features; avoid float conversion of large integers.
    features = {}
    for name, value in body.features.model_dump().items():
        if type(value) in (int, float):
            numerator, denominator = (value, 1) if type(value) is int else value.as_integer_ratio()
            value = {"numerator": str(numerator), "denominator": str(denominator)}
        features[name] = value
    input_sha = digest({"contract": body.feature_contract_version, "features": features})
    request_sha = digest(
        {
            "source_id": body.source_id,
            "classification": body.data_classification,
            "input_sha256": input_sha,
        }
    )
    return input_sha, request_sha


def unique_request_race(error: IntegrityError) -> bool:
    original = error.orig
    if getattr(original, "sqlstate", None) == "23505":
        return getattr(getattr(original, "diag", None), "constraint_name", None) in {
            "alerts_source_id_key",
            "uq_alert_ingestions_key",
        }
    return getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE" and str(
        original
    ) in {
        "UNIQUE constraint failed: alerts.source_id",
        "UNIQUE constraint failed: alert_ingestions.key_sha256",
    }


def ingest_alert(
    session: Session, body: AlertIngestionInput, key: str, actor_id: UUID
) -> tuple[dict, bool]:
    # Authentication may already have begun this request's session transaction.
    # Commit exactly once; rollback the whole transaction on every failure.
    for attempt in range(2):
        try:
            result = ingest_alert_in_transaction(session, body, key, actor_id)
            session.commit()
            return result
        except IntegrityError as error:
            session.rollback()
            # Unique constraints arbitrate simultaneous requests, never process-local locks.
            if attempt == 0 and unique_request_race(error):
                continue
            raise
        except BaseException:
            session.rollback()
            raise
    raise AssertionError("Unreachable ingestion state")


def ingest_alert_in_transaction(
    session: Session, body: AlertIngestionInput, key: str, actor_id: UUID
) -> tuple[dict, bool]:
    """Caller owns authorization, transaction and unique-race/savepoint handling."""
    input_sha, request_sha = fingerprints(body)
    key_sha = hashlib.sha256(key.encode()).hexdigest()
    prior = session.scalar(select(AlertIngestion).where(AlertIngestion.key_sha256 == key_sha))
    if prior is not None:
        if prior.request_sha256 != request_sha:
            raise IngestionConflict("Idempotency key was used for different content")
        response = dict(prior.response_json)
        return response, False
    alert = session.scalar(select(Alert).where(Alert.source_id == body.source_id))
    created = alert is None
    if alert is None:
        alert = Alert(
            source_id=body.source_id,
            data_classification=body.data_classification,
            feature_contract_version=body.feature_contract_version,
            features=body.features.model_dump(),
            input_sha256=input_sha,
        )
        session.add(alert)
        session.flush()
        case = Case(alert_id=alert.id, status="open", disposition=None)
        session.add(case)
        session.flush()
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action="alert.ingested",
                resource_id=str(alert.id),
                details={
                    "case_id": str(case.id),
                    "input_sha256": input_sha,
                    "feature_contract_version": body.feature_contract_version,
                },
            )
        )
        session.flush()
    else:
        if (
            alert.input_sha256 != input_sha
            or alert.feature_contract_version != body.feature_contract_version
            or alert.data_classification != body.data_classification
        ):
            raise IngestionConflict("Source identifier was used for different content")
        case = session.scalar(select(Case).where(Case.alert_id == alert.id))
        if case is None:
            raise IngestionStateError("Stored alert is missing its case")
    response = {
        "alert_id": str(alert.id),
        "case_id": str(case.id),
        "case_status": "open",
        "scoring_status": "not_requested",
        "routing_status": "not_evaluated",
        "feature_contract_version": body.feature_contract_version,
    }
    session.add(
        AlertIngestion(
            key_sha256=key_sha,
            request_sha256=request_sha,
            alert_id=alert.id,
            case_id=case.id,
            created_by=actor_id,
            response_json=response,
        )
    )
    session.flush()
    return response, created
