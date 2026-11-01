"""Internal assessment service. No HTTP, automatic case action, or untrusted result submission."""

import hashlib
import math
import re
from dataclasses import asdict
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Assessment,
    AssessmentExplanation,
    AuditEvent,
    Case,
    Decision,
    ModelScore,
    User,
)
from app.models.domain import utcnow
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures, AlertIngestionInput
from app.services.ingestion import digest, fingerprints
from trueflag_ml.explanation_contract import (
    GROUP_ATOL,
    INPUT_HASH_SCHEMA,
    RECONSTRUCTION_ATOL,
    SCORE_ATOL,
    ExplanationMethod,
    ExplanationResult,
    FeatureContribution,
    input_digest,
)
from trueflag_ml.policy import MODES, POLICY_SHA256, RiskPolicyEngine
from trueflag_ml.scoring import ScoreResult, ScoringRecord
from trueflag_ml.trust import (
    APPROVED_SHA256,
    CONTRACT_PATH,
    MODEL_PATH,
    MODEL_VERSION,
    REQUIRED_VERSIONS,
)

PERSISTENCE_SCHEMA = "trueflag.assessment.v1"
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", re.ASCII)


class AssessmentError(Exception):
    """Only stable reason codes cross the service boundary."""


class AssessmentNotFound(AssessmentError):
    pass


class AssessmentConflict(AssessmentError):
    pass


class AssessmentUnavailable(AssessmentError):
    pass


def _arguments(actor_id, case_id, expected_version, run_id, key, policy):
    if (
        any(type(value) is not UUID for value in (actor_id, case_id, run_id))
        or type(expected_version) is not int
        or not 1 <= expected_version <= 2**31 - 1
        or type(key) is not str
        or not _KEY.fullmatch(key)
        or type(policy) is not str
        or policy not in MODES
    ):
        raise AssessmentError("invalid_assessment_request")


def _locked_case(session, actor_id, case_id):
    # Same lock order as assignment: user -> case -> alert. Never trust cached role claims.
    user = session.scalar(
        select(User)
        .where(
            User.id == actor_id,
            User.active.is_(True),
            User.role.in_(["analyst", "supervisor", "admin"]),
        )
        .with_for_update(read=True)
    )
    if user is None:
        raise AssessmentNotFound("assessment_not_found")
    query = select(Case).where(Case.id == case_id)
    if user.role == "analyst":
        query = query.where(Case.assigned_to == actor_id)
    case = session.scalar(query.with_for_update())
    if case is None:
        raise AssessmentNotFound("assessment_not_found")
    return case


def _snapshot(session, case):
    alert = session.scalar(
        select(Alert).where(Alert.id == case.alert_id).with_for_update(read=True)
    )
    try:
        if (
            alert is None
            or alert.data_classification != "synthetic"
            or alert.feature_contract_version != FEATURE_CONTRACT_VERSION
        ):
            raise ValueError
        features = AlertFeatures.model_validate(alert.features).model_dump()
        body = AlertIngestionInput(
            source_id=alert.source_id,
            data_classification=alert.data_classification,
            feature_contract_version=alert.feature_contract_version,
            features=features,
        )
        if fingerprints(body)[0] != alert.input_sha256:
            raise ValueError
        record = ScoringRecord(str(case.id), features)
        return {
            "alert_id": str(alert.id),
            "case_version": case.version,
            "case_status": case.status,
            "disposition": case.disposition,
            "assigned_to": str(case.assigned_to) if case.assigned_to else None,
            "feature_contract_version": alert.feature_contract_version,
            "ingestion_input_sha256": alert.input_sha256,
            "source_id_sha256": hashlib.sha256(alert.source_id.encode()).hexdigest(),
            "input_sha256": input_digest(record),
            "input_hash_schema": INPUT_HASH_SCHEMA,
        }, features
    except Exception:
        raise AssessmentUnavailable("assessment_input_unavailable") from None


def _request(actor_id, case_id, version, run_id, policy, snapshot):
    return digest(
        {
            "schema": PERSISTENCE_SCHEMA,
            "actor_id": str(actor_id),
            "case_id": str(case_id),
            "expected_version": version,
            "run_id": str(run_id),
            "policy": policy,
            "input_sha256": snapshot["input_sha256"],
            "ingestion_input_sha256": snapshot["ingestion_input_sha256"],
            "source_id_sha256": snapshot["source_id_sha256"],
            "model_sha256": APPROVED_SHA256[MODEL_PATH],
            "policy_sha256": POLICY_SHA256,
        }
    )


def _prior(session, key_sha, run_id, request_sha):
    rows = session.scalars(
        select(Assessment).where(
            or_(
                Assessment.key_sha256 == key_sha,
                Assessment.run_id == run_id,
            )
        )
    ).all()
    if not rows:
        return None
    if (
        len(rows) != 1
        or rows[0].key_sha256 != key_sha
        or rows[0].run_id != run_id
        or rows[0].request_sha256 != request_sha
    ):
        raise AssessmentConflict("assessment_idempotency_conflict")
    return rows[0]


def _content(assessment, score, decision, explanation, audit):
    # Includes all persisted business fields and child identities; excludes the digest itself.
    return {
        "schema": PERSISTENCE_SCHEMA,
        "assessment_id": str(assessment.id),
        "run_id": str(assessment.run_id),
        "case_id": str(assessment.case_id),
        "alert_id": str(assessment.alert_id),
        "actor_id": str(assessment.actor_id),
        "version": assessment.version,
        "case_version": assessment.case_version,
        "status": assessment.status,
        "key_sha256": assessment.key_sha256,
        "request_sha256": assessment.request_sha256,
        "input_sha256": assessment.input_sha256,
        "provenance": assessment.provenance,
        "score_id": str(score.id),
        "decision_id": str(decision.id),
        "explanation_id": str(explanation.id),
        "audit_event_id": str(audit.id),
        "recorded_at": {
            name: (
                row.created_at.replace(tzinfo=timezone.utc)
                if row.created_at.tzinfo is None
                else row.created_at.astimezone(timezone.utc)
            ).isoformat()
            for name, row in (
                ("assessment", assessment),
                ("score", score),
                ("decision", decision),
                ("explanation", explanation),
                ("audit", audit),
            )
        },
        "score": {
            "alert_id": str(score.alert_id),
            "model_version": score.model_version,
            "model_sha256": score.model_sha256,
            "input_sha256": score.input_sha256,
            "status": score.status,
            "score": score.score,
            "failure_code": score.failure_code,
        },
        "decision": {
            "score_id": str(decision.score_id),
            "policy_version": decision.policy_version,
            "mode": decision.mode,
            "route": decision.route,
            "processing_status": decision.processing_status,
            "reason_code": decision.reason_code,
        },
        "explanation": explanation.payload,
        "verification": explanation.verification,
        "audit": {
            "actor_id": str(audit.actor_id),
            "action": audit.action,
            "resource_id": audit.resource_id,
        },
    }


def _read(session, assessment):
    try:
        score = session.get(ModelScore, assessment.score_id)
        decision = session.get(Decision, assessment.decision_id)
        explanation = session.get(AssessmentExplanation, assessment.explanation_id)
        audit = session.get(AuditEvent, assessment.audit_event_id)
        content = _content(assessment, score, decision, explanation, audit)
        expected_audit = {
            "assessment_id": str(assessment.id),
            "case_id": str(assessment.case_id),
            "run_id": str(assessment.run_id),
            "assessment_version": assessment.version,
            "content_sha256": assessment.content_sha256,
        }
        if digest(content) != assessment.content_sha256 or audit.details != expected_audit:
            raise ValueError
        return {**content, "content_sha256": assessment.content_sha256}
    except Exception:
        raise AssessmentUnavailable("assessment_integrity_failed") from None


class AssessmentService:
    def __init__(self, engine, artifact_root=None):
        self.engine = engine
        self.artifact_root = artifact_root

    def _compute(self, actor_id, case_id, features, policy):
        # This is a trusted internal producer; there is no submission endpoint or result parameter.
        from trueflag_ml.explainability import ExplanationService
        from trueflag_ml.explanation_verification import verify_explanation

        def authorize(ident):
            if ident != str(case_id):
                return False
            try:
                with Session(self.engine) as session, session.begin():
                    _locked_case(session, actor_id, case_id)
                return True
            except Exception:
                return False

        explainer = ExplanationService(authorize, self.artifact_root)
        record = ScoringRecord(str(case_id), features)
        score = explainer._scorer.score_one(record.record_id, features)
        explanation = explainer.explain_one(record.record_id, features)
        if explanation.status != "verified":
            raise AssessmentUnavailable("assessment_explanation_unavailable")
        verified = verify_explanation(
            explanation,
            record,
            score,
            explainer._loaded,
            explainer.encoded_to_original,
        )
        engine = RiskPolicyEngine(self.artifact_root)
        recommendation = engine.evaluate(score, policy, kyc_risk_score=features["kycRiskScore"])
        if recommendation.processing_status != "processed":
            raise AssessmentUnavailable("assessment_policy_unavailable")
        policy_payload = asdict(recommendation)
        policy_payload.pop("kyc_risk_score")  # Do not duplicate a raw predictor in provenance.
        return {
            "score": asdict(score),
            "policy": policy_payload,
            "explanation": asdict(verified),
            "verification": {
                "status": "verified",
                "verifier": "trueflag.independent-explanation.v1",
                "score_atol": SCORE_ATOL,
                "group_atol": GROUP_ATOL,
                "reconstruction_atol": RECONSTRUCTION_ATOL,
                "rtol": 0,
                "encoded_to_original": list(explainer.encoded_to_original),
                "independent_model_and_root_checks": True,
                "runtime_dependencies": dict(explainer._loaded.dependencies),
                "approved_artifact_identities": dict(APPROVED_SHA256),
            },
        }

    def assess(self, *, actor_id, case_id, expected_version, run_id, idempotency_key, policy):
        _arguments(actor_id, case_id, expected_version, run_id, idempotency_key, policy)
        key_sha = digest({"actor_id": str(actor_id), "key": idempotency_key})
        try:
            with Session(self.engine) as session, session.begin():
                case = _locked_case(session, actor_id, case_id)
                snapshot, features = _snapshot(session, case)
                request_sha = _request(
                    actor_id, case_id, expected_version, run_id, policy, snapshot
                )
                prior = _prior(session, key_sha, run_id, request_sha)
                if prior is not None:
                    return _read(session, prior), False
                if case.version != expected_version or case.status == "closed":
                    raise AssessmentConflict("assessment_stale_case")
            # No transaction, row lock, or DB session spans expensive model execution.
            result = self._compute(actor_id, case_id, features, policy)
            self._validate_result(result, case_id, features, policy, snapshot)
            for attempt in range(2):
                try:
                    return self._persist(
                        actor_id,
                        case_id,
                        expected_version,
                        run_id,
                        key_sha,
                        request_sha,
                        snapshot,
                        result,
                    )
                except IntegrityError as error:
                    name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                    if name not in {"uq_assessment_run", "uq_assessment_key"}:
                        raise
                    if attempt:
                        raise AssessmentConflict("assessment_idempotency_conflict") from None
            raise AssertionError
        except AssessmentError:
            raise
        except SQLAlchemyError:
            raise AssessmentUnavailable("assessment_database_unavailable") from None
        except Exception:
            raise AssessmentUnavailable("assessment_processing_unavailable") from None

    def _validate_result(self, result, case_id, features, policy, snapshot):
        try:
            # Strict serialization rejects non-finite output; no feature values enter the payload.
            digest(result)
            score = ScoreResult(**result["score"])
            expected_policy = RiskPolicyEngine(self.artifact_root).evaluate(
                score,
                policy,
                kyc_risk_score=features["kycRiskScore"],
            )
            expected = asdict(expected_policy)
            expected.pop("kyc_risk_score")
            e = result["explanation"]
            v = result["verification"]
            # Reject accidental raw-value/extra-field leakage in nested result objects.
            if set(result) != {"score", "policy", "explanation", "verification"}:
                raise ValueError
            decoded = dict(e)
            decoded["method"] = ExplanationMethod(**e["method"])
            decoded["features"] = tuple(FeatureContribution(**f) for f in e["features"])
            ExplanationResult(**decoded)
            if (
                result["policy"] != expected
                or expected_policy.processing_status != "processed"
                or score.record_id != str(case_id)
                or e["record_id"] != str(case_id)
                or score.model_version != MODEL_VERSION
                or score.model_sha256 != APPROVED_SHA256[MODEL_PATH]
                or e["model_version"] != score.model_version
                or e["model_sha256"] != score.model_sha256
                or e["contract_sha256"] != APPROVED_SHA256[CONTRACT_PATH]
                or e["status"] != "verified"
                or e["reason"] is not None
                or e["input_sha256"] != snapshot["input_sha256"]
                or e["input_hash_schema"] != INPUT_HASH_SCHEMA
                or e["method"] != asdict(ExplanationMethod())
                or type(e["model_score"]) is not float
                or e["model_score"] != score.score
                or type(e["base_value"]) is not float
                or not math.isfinite(e["base_value"])
                or len(e["encoded_contributions"]) != 41
                or len(e["features"]) != 27
                or tuple(f["name"] for f in e["features"]) != tuple(AlertFeatures.model_fields)
                or v["status"] != "verified"
                or v["verifier"] != "trueflag.independent-explanation.v1"
                or v["score_atol"] != SCORE_ATOL
                or v["group_atol"] != GROUP_ATOL
                or v["reconstruction_atol"] != RECONSTRUCTION_ATOL
                or v["rtol"] != 0
                or v["independent_model_and_root_checks"] is not True
                or v["runtime_dependencies"] != dict(REQUIRED_VERSIONS)
                or v["approved_artifact_identities"] != dict(APPROVED_SHA256)
                or len(v["encoded_to_original"]) != 41
            ):
                raise ValueError
            if set(v) != {
                "status",
                "verifier",
                "score_atol",
                "group_atol",
                "reconstruction_atol",
                "rtol",
                "encoded_to_original",
                "independent_model_and_root_checks",
                "runtime_dependencies",
                "approved_artifact_identities",
            }:
                raise ValueError
            # Recheck both contribution levels at the persistence boundary.
            for f in e["features"]:
                grouped = math.fsum(
                    x
                    for x, name in zip(
                        e["encoded_contributions"],
                        v["encoded_to_original"],
                        strict=True,
                    )
                    if name == f["name"]
                )
                if (
                    type(f["contribution"]) is not float
                    or abs(grouped - f["contribution"]) > GROUP_ATOL
                    or f["missing"] is not (features[f["name"]] is None)
                ):
                    raise ValueError
            for contributions in (
                e["encoded_contributions"],
                [f["contribution"] for f in e["features"]],
            ):
                if any(type(x) is not float or not math.isfinite(x) for x in contributions):
                    raise ValueError
                if (
                    abs(e["base_value"] + math.fsum(contributions) - score.score)
                    > RECONSTRUCTION_ATOL
                ):
                    raise ValueError
        except Exception:
            raise AssessmentUnavailable("assessment_result_invalid") from None

    def _persist(self, actor_id, case_id, version, run_id, key_sha, request_sha, snapshot, result):
        with Session(self.engine) as session, session.begin():
            case = _locked_case(session, actor_id, case_id)
            current, _ = _snapshot(session, case)
            if current["input_sha256"] != snapshot["input_sha256"]:
                raise AssessmentConflict("assessment_stale_input")
            prior = _prior(session, key_sha, run_id, request_sha)
            if prior is not None:
                return _read(session, prior), False
            if current != snapshot or case.version != version or case.status == "closed":
                raise AssessmentConflict("assessment_stale_case")
            next_version = 1 + (
                session.scalar(
                    select(func.max(Assessment.version)).where(
                        Assessment.case_id == case_id,
                    )
                )
                or 0
            )
            now = utcnow()
            s, p = result["score"], result["policy"]
            score = ModelScore(
                id=uuid4(),
                created_at=now,
                alert_id=case.alert_id,
                model_version=s["model_version"],
                model_sha256=s["model_sha256"],
                input_sha256=snapshot["input_sha256"],
                status="processed",
                score=s["score"],
            )
            session.add(score)
            session.flush()
            decision = Decision(
                id=uuid4(),
                created_at=now,
                score_id=score.id,
                policy_version=p["policy_version"],
                mode=p["selected_policy"],
                route=p["recommended_route"],
                processing_status="processed",
                reason_code=p["routing_reason"],
            )
            explanation = AssessmentExplanation(
                id=uuid4(),
                created_at=now,
                payload=result["explanation"],
                verification=result["verification"],
            )
            audit = AuditEvent(
                id=uuid4(),
                created_at=now,
                actor_id=actor_id,
                action="assessment.completed",
                resource_id=str(case_id),
                details={},
            )
            session.add_all([decision, explanation, audit])
            session.flush()
            assessment = Assessment(
                id=uuid4(),
                created_at=now,
                case_id=case_id,
                alert_id=case.alert_id,
                actor_id=actor_id,
                run_id=run_id,
                version=next_version,
                case_version=version,
                status="completed",
                key_sha256=key_sha,
                request_sha256=request_sha,
                input_sha256=snapshot["input_sha256"],
                score_id=score.id,
                decision_id=decision.id,
                explanation_id=explanation.id,
                audit_event_id=audit.id,
                provenance={
                    "schema": PERSISTENCE_SCHEMA,
                    "processed_at": now.isoformat(),
                    "snapshot": snapshot,
                    "policy": p,
                    "contract_sha256": APPROVED_SHA256[CONTRACT_PATH],
                    "producer": "trueflag.phase2.5.verified-rf-shap.v1",
                    "human_decision_required": True,
                },
            )
            assessment.content_sha256 = digest(
                _content(assessment, score, decision, explanation, audit)
            )
            audit.details = {
                "assessment_id": str(assessment.id),
                "case_id": str(case_id),
                "run_id": str(run_id),
                "assessment_version": next_version,
                "content_sha256": assessment.content_sha256,
            }
            # Audit update must flush BEFORE its protecting assessment link is inserted.
            session.flush()
            session.add(assessment)
            session.flush()
            return _read(session, assessment), True

    def get(self, *, actor_id, case_id, assessment_id):
        if any(type(x) is not UUID for x in (actor_id, case_id, assessment_id)):
            raise AssessmentError("invalid_assessment_request")
        try:
            with Session(self.engine) as session, session.begin():
                _locked_case(session, actor_id, case_id)
                assessment = session.scalar(
                    select(Assessment).where(
                        Assessment.id == assessment_id,
                        Assessment.case_id == case_id,
                    )
                )
                if assessment is None:
                    raise AssessmentNotFound("assessment_not_found")
                return _read(session, assessment)
        except SQLAlchemyError:
            raise AssessmentUnavailable("assessment_database_unavailable") from None

    def list(self, *, actor_id, case_id, limit=20, offset=0):
        if (
            type(actor_id) is not UUID
            or type(case_id) is not UUID
            or type(limit) is not int
            or not 1 <= limit <= 50
            or type(offset) is not int
            or not 0 <= offset <= 100000
        ):
            raise AssessmentError("invalid_assessment_request")
        try:
            with Session(self.engine) as session, session.begin():
                _locked_case(session, actor_id, case_id)
                rows = session.scalars(
                    select(Assessment)
                    .where(Assessment.case_id == case_id)
                    .order_by(Assessment.version.desc())
                    .limit(limit)
                    .offset(offset)
                )
                return tuple(_read(session, row) for row in rows)
        except SQLAlchemyError:
            raise AssessmentUnavailable("assessment_database_unavailable") from None
