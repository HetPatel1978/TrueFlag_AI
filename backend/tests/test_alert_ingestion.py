import copy
import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_foundation import headers

from app.main import create_app
from app.models import Alert, AlertIngestion, AuditEvent, Case, Decision, ModelScore, User


def counts(engine):
    with Session(engine) as session:
        result = [
            session.scalar(select(func.count()).select_from(model))
            for model in [Alert, Case, AlertIngestion, ModelScore, Decision]
        ]
        result.append(
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "alert.ingested")
            )
        )
    return result


def test_ingestion_persists_atomic_records_without_scoring(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == 201
    receipt = response.json()
    assert receipt["case_status"] == "open"
    assert receipt["scoring_status"] == "not_requested"
    assert receipt["routing_status"] == "not_evaluated"
    assert "features" not in receipt and "score" not in receipt
    assert counts(engine) == [1, 1, 1, 0, 0, 1]
    with Session(engine) as session:
        alert = session.scalar(select(Alert))
        case = session.scalar(select(Case))
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "alert.ingested"))
        recorded = session.scalar(select(AlertIngestion))
        actor = session.scalar(select(User).where(User.username == "admin"))
        assert alert.features == alert_payload["features"]
        assert alert.features["income"] is None
        assert str(case.alert_id) == str(alert.id) == receipt["alert_id"]
        assert case.status == "open" and case.disposition is None and case.assigned_to is None
        assert audit.actor_id == recorded.created_by == actor.id
        assert audit.details["case_id"] == receipt["case_id"]
        assert (
            recorded.key_sha256
            == hashlib.sha256(admin_headers["Idempotency-Key"].encode()).hexdigest()
        )
        assert recorded.response_json == receipt
        assert "features" not in audit.details
        assert admin_headers["Idempotency-Key"] not in json.dumps(audit.details)


def test_repeat_request_returns_original_receipt(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform
    first = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    for _ in range(3):
        replay = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
        assert replay.status_code == 200 and replay.json() == first.json()
    assert counts(engine) == [1, 1, 1, 0, 0, 1]


def test_changed_key_same_source_is_deduplicated(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform
    first = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    admin_headers["Idempotency-Key"] = str(uuid4())
    second = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert second.status_code == 200 and second.json() == first.json()
    assert counts(engine) == [1, 1, 2, 0, 0, 1]


@pytest.mark.parametrize("reuse_key,change_source", [(True, False), (False, False), (True, True)])
def test_conflicting_payloads_rejected(
    platform, alert_payload, admin_headers, reuse_key, change_source
):
    client, engine, _, _ = platform
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 201
    )
    if not reuse_key:
        admin_headers["Idempotency-Key"] = str(uuid4())
    if change_source:
        alert_payload["source_id"] = "different-source"
    else:
        alert_payload["features"]["income"] = 0
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == 409
    assert counts(engine) == [1, 1, 1, 0, 0, 1]


def test_different_sources_are_not_deduplicated_by_features(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 201
    )
    alert_payload["source_id"] = "independent-source"
    admin_headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 201
    )
    assert counts(engine) == [2, 2, 2, 0, 0, 2]


def test_numeric_equivalent_retry_and_restart(platform, alert_payload, admin_headers):
    client, engine, settings, _ = platform
    first = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    equivalent = copy.deepcopy(alert_payload)
    equivalent["features"].update(kycRiskScore=3.0, PEP=-0.0)
    with TestClient(create_app(settings, engine)) as restarted:
        replay = restarted.post("/api/v1/alerts", json=equivalent, headers=admin_headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert counts(engine) == [1, 1, 1, 0, 0, 1]


@pytest.mark.parametrize("target", ["alerts", "cases", "audit_events", "alert_ingestions"])
def test_database_failure_rolls_back_every_record_and_allows_retry(
    platform, alert_payload, admin_headers, target
):
    client, engine, _, _ = platform

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().lower().startswith("insert into " + target):
            raise OperationalError("injected failure", None, RuntimeError("synthetic test failure"))

    event.listen(engine, "before_cursor_execute", fail)
    try:
        response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
        assert response.status_code == 503
        assert response.json() == {"detail": "Database operation unavailable"}
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert counts(engine) == [0, 0, 0, 0, 0, 0]
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 201
    )
    assert counts(engine) == [1, 1, 1, 0, 0, 1]


def test_commit_failure_never_returns_success(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform

    def fail(connection):
        raise OperationalError("injected commit failure", None, RuntimeError("test failure"))

    event.listen(engine, "commit", fail)
    try:
        assert (
            client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code
            == 503
        )
    finally:
        event.remove(engine, "commit", fail)
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize("identity,status", [(None, 401), ("analyst", 403)])
def test_unauthorized_ingestion_writes_nothing(platform, alert_payload, identity, status):
    client, engine, _, _ = platform
    auth = headers(platform, identity) if identity else {}
    response = client.post(
        "/api/v1/alerts", json=alert_payload, headers={**auth, "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == status
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize("key", [None, "short", "x" * 129, "invalid key with spaces"])
def test_required_key_validation(platform, alert_payload, admin_headers, key):
    client, engine, _, _ = platform
    admin_headers.pop("Idempotency-Key")
    if key is not None:
        admin_headers["Idempotency-Key"] = key
    assert (
        client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers).status_code == 422
    )
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize(
    "mutation",
    [
        "real_data",
        "wrong_contract",
        "extra_envelope",
        "missing_income",
        "extra_label",
        "numeric_string",
        "invalid_kyc",
    ],
)
def test_invalid_requests_do_not_persist(platform, alert_payload, admin_headers, mutation):
    client, engine, _, _ = platform
    if mutation == "real_data":
        alert_payload["data_classification"] = "real"
    if mutation == "wrong_contract":
        alert_payload["feature_contract_version"] = "other"
    if mutation == "extra_envelope":
        alert_payload["actor"] = "admin"
    if mutation == "missing_income":
        del alert_payload["features"]["income"]
    if mutation == "extra_label":
        alert_payload["features"]["SAR"] = "private-marker-should-not-be-reflected"
    if mutation == "numeric_string":
        alert_payload["features"]["income"] = "private-marker-should-not-be-reflected"
    if mutation == "invalid_kyc":
        alert_payload["features"]["kycRiskScore"] = 7
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == 422
    assert "private-marker" not in response.text
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


def test_nonfinite_json_errors_are_safe(platform, alert_payload, admin_headers):
    client, engine, _, _ = platform
    alert_payload["features"]["income"] = float("nan")
    response = client.post(
        "/api/v1/alerts",
        content=json.dumps(alert_payload),
        headers={**admin_headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 422 and "NaN" not in response.text
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


@pytest.mark.parametrize("change", ["deactivate", "demote"])
def test_current_database_permissions_apply_to_ingestion(
    platform, alert_payload, admin_headers, change
):
    client, engine, _, _ = platform
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.username == "admin"))
        if change == "deactivate":
            user.active = False
        else:
            user.role = "analyst"
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == (401 if change == "deactivate" else 403)
    assert counts(engine) == [0, 0, 0, 0, 0, 0]


def test_existing_case_is_never_reopened_by_duplicate_ingestion(
    platform, alert_payload, admin_headers
):
    client, engine, _, _ = platform
    first = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    with Session(engine) as session, session.begin():
        case = session.scalar(select(Case))
        case.status = "closed"
        case.disposition = "close"
    admin_headers["Idempotency-Key"] = str(uuid4())
    response = client.post("/api/v1/alerts", json=alert_payload, headers=admin_headers)
    assert response.status_code == 200 and response.json() == first.json()
    with Session(engine) as session:
        case = session.scalar(select(Case))
        assert case.status == "closed" and case.disposition == "close"
