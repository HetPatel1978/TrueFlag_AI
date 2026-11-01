"""Persistence-only synthetic producers; real RF/SHAP acceptance is a separate Linux test."""

import copy
import json
from dataclasses import asdict
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import app.services.assessments as module
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
from app.schemas.alerts import AlertFeatures
from app.services.assessments import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
    AssessmentService,
    AssessmentUnavailable,
)
from trueflag_ml.explanation_contract import ExplanationResult, FeatureContribution, input_digest
from trueflag_ml.policy import FrozenPolicySet, RiskPolicyEngine
from trueflag_ml.scoring import ScoreResult, ScoringRecord
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION, REQUIRED_VERSIONS


@pytest.fixture
def assessment_setup(platform, case_team, monkeypatch):
    # Frozen synthetic policy config enables DB acceptance without any private assets/dependencies.
    rules = object.__new__(RiskPolicyEngine)
    rules.load_failure = None
    rules._settings = FrozenPolicySet(
        MappingProxyType(
            {
                "Efficiency": 0.19088491043724937,
                "Balanced": 0.16040515630453706,
                "Coverage": 0.16040515630453706,
            }
        ),
        MappingProxyType({"Standard": (0, 1, 2), "High": (3, 4, 5, 6)}),
    )
    monkeypatch.setattr(module, "RiskPolicyEngine", lambda *args: rules)
    service = AssessmentService(platform[1])
    calls = []

    def compute(actor, case, features, policy):
        calls.append(case)
        return synthetic_result(case, features, policy, rules)

    monkeypatch.setattr(service, "_compute", compute)
    request = {
        "actor_id": UUID(case_team["users"]["analyst"]),
        "case_id": UUID(case_team["ids"][0]),
        "expected_version": 1,
        "run_id": uuid4(),
        "idempotency_key": "synthetic-assessment-key",
        "policy": "Coverage",
    }
    return service, request, calls


def synthetic_result(case, features, policy, rules):
    score = ScoreResult(str(case), 0.15, MODEL_VERSION, APPROVED_SHA256[MODEL_PATH], "processed")
    p = asdict(rules.evaluate(score, policy, kyc_risk_score=features["kycRiskScore"]))
    p.pop("kyc_risk_score")
    fields = tuple(AlertFeatures.model_fields)
    mapping = (
        ["state"] * 9
        + ["kycRiskScore"] * 7
        + [f for f in fields if f not in {"state", "kycRiskScore"}]
    )
    encoded = [-0.05] + [0.0] * 40
    grouped = tuple(
        FeatureContribution(
            name,
            -0.05 if name == "state" else 0.0,
            "lowers_score" if name == "state" else "no_contribution",
            features[name] is None,
        )
        for name in fields
    )
    ranking = tuple(
        sorted(fields, key=lambda f: (-abs(-0.05 if f == "state" else 0), fields.index(f)))
    )
    e = ExplanationResult(
        str(case),
        "verified",
        input_sha256=input_digest(ScoringRecord(str(case), features)),
        model_score=score.score,
        base_value=0.2,
        encoded_contributions=tuple(encoded),
        features=grouped,
        ranking=ranking,
        top_features=("state",),
        other_features_contribution=0.0,
        reconstruction_residual=0.2 - 0.05 - score.score,
    )
    return {
        "score": asdict(score),
        "policy": p,
        "explanation": asdict(e),
        "verification": {
            "status": "verified",
            "verifier": "trueflag.independent-explanation.v1",
            "score_atol": 1e-12,
            "group_atol": 1e-12,
            "reconstruction_atol": 1e-6,
            "rtol": 0,
            "encoded_to_original": mapping,
            "independent_model_and_root_checks": True,
            "runtime_dependencies": dict(REQUIRED_VERSIONS),
            "approved_artifact_identities": dict(APPROVED_SHA256),
        },
    }


def counts(engine):
    with Session(engine) as session:
        return [
            session.scalar(select(func.count()).select_from(model))
            for model in (
                Assessment,
                AssessmentExplanation,
                ModelScore,
                Decision,
            )
        ] + [
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action == "assessment.completed",
                )
            )
        ]


def test_persistence_and_provenance(platform, case_team, assessment_setup):
    service, request, calls = assessment_setup
    result, created = service.assess(**request)
    assert created and len(calls) == 1 and counts(platform[1]) == [1] * 5
    assert result["version"] == 1 and result["status"] == "completed"
    assert result["decision"]["route"] == "retain_human_review"
    assert result["provenance"]["policy"]["override_reason"] == "coverage_high_priority_protection"
    assert result["score"]["input_sha256"] == result["input_sha256"]
    assert result["explanation"]["input_sha256"] == result["input_sha256"]
    assert len(result["content_sha256"]) == 64
    loaded = service.get(
        actor_id=request["actor_id"],
        case_id=request["case_id"],
        assessment_id=UUID(result["assessment_id"]),
    )
    assert json.dumps(result, sort_keys=True) == json.dumps(loaded, sort_keys=True)
    assert service.list(actor_id=request["actor_id"], case_id=request["case_id"])[0] == loaded
    stored = json.dumps(loaded)
    assert "kyc_risk_score" not in stored and "synthetic-assessment-key" not in stored
    assert '"source_id"' not in stored
    assert all(
        set(f) == {"name", "contribution", "direction", "missing"}
        for f in loaded["explanation"]["features"]
    )
    with Session(platform[1]) as session:
        case = session.get(Case, request["case_id"])
        assert case.version == 1 and case.status == "open" and case.disposition is None


def test_retry_and_reassessment(platform, assessment_setup):
    service, request, calls = assessment_setup
    first, _ = service.assess(**request)
    again, created = service.assess(**request)
    assert (
        again
        == service.get(
            actor_id=request["actor_id"],
            case_id=request["case_id"],
            assessment_id=UUID(first["assessment_id"]),
        )
        and not created
    )
    assert len(calls) == 1 and counts(platform[1]) == [1] * 5
    second, created = service.assess(
        **{**request, "run_id": uuid4(), "idempotency_key": "next-run-key"}
    )
    assert created and second["version"] == 2 and first["assessment_id"] != second["assessment_id"]
    assert counts(platform[1]) == [2] * 5
    assert [
        r["version"] for r in service.list(actor_id=request["actor_id"], case_id=request["case_id"])
    ] == [2, 1]
    assert (
        len(
            service.list(
                actor_id=request["actor_id"], case_id=request["case_id"], limit=1, offset=1
            )
        )
        == 1
    )


@pytest.mark.parametrize("change", ["policy", "run", "key", "version"])
def test_idempotency_conflict(platform, assessment_setup, change):
    service, request, _ = assessment_setup
    service.assess(**request)
    mutation = {
        "policy": {"policy": "Balanced"},
        "run": {"run_id": uuid4()},
        "key": {"idempotency_key": "different-key"},
        "version": {"expected_version": 2},
    }[change]
    with pytest.raises(AssessmentConflict, match="idempotency_conflict"):
        service.assess(**{**request, **mutation})
    assert counts(platform[1]) == [1] * 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_version", True),
        ("expected_version", 0),
        ("expected_version", 2**40),
        ("policy", "coverage"),
        ("idempotency_key", "short"),
        ("idempotency_key", "secret\nkey"),
        ("run_id", "client-value"),
        ("actor_id", None),
    ],
)
def test_invalid_envelope(assessment_setup, field, value):
    service, request, calls = assessment_setup
    with pytest.raises(AssessmentError, match="invalid_assessment_request"):
        service.assess(**{**request, field: value})
    assert not calls


@pytest.mark.parametrize("actor", ["analysttwo", "inactive", "missing"])
def test_unauthorized_no_inference(platform, case_team, assessment_setup, actor):
    service, request, calls = assessment_setup
    actor_id = uuid4() if actor == "missing" else UUID(case_team["users"][actor])
    with pytest.raises(AssessmentNotFound, match="assessment_not_found"):
        service.assess(**{**request, "actor_id": actor_id})
    assert not calls and counts(platform[1]) == [0] * 5


@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_manager_access(case_team, assessment_setup, role):
    service, request, _ = assessment_setup
    result, _ = service.assess(**{**request, "actor_id": UUID(case_team["users"][role])})
    assert result["actor_id"] == case_team["users"][role]


def test_read_isolation_and_revocation(platform, case_team, assessment_setup):
    service, request, _ = assessment_setup
    result, _ = service.assess(**request)
    assessment_id = UUID(result["assessment_id"])
    for actor in [UUID(case_team["users"]["analysttwo"]), uuid4()]:
        with pytest.raises(AssessmentNotFound):
            service.get(actor_id=actor, case_id=request["case_id"], assessment_id=assessment_id)
        with pytest.raises(AssessmentNotFound):
            service.list(actor_id=actor, case_id=request["case_id"])
    with pytest.raises(AssessmentNotFound):
        service.get(
            actor_id=UUID(case_team["users"]["admin"]),
            case_id=UUID(case_team["ids"][1]),
            assessment_id=assessment_id,
        )
    with Session(platform[1]) as session, session.begin():
        session.get(User, request["actor_id"]).active = False
    for operation in [
        lambda: service.assess(**request),
        lambda: service.get(
            actor_id=request["actor_id"], case_id=request["case_id"], assessment_id=assessment_id
        ),
    ]:
        with pytest.raises(AssessmentNotFound):
            operation()


@pytest.mark.parametrize(
    "change",
    ["reassign", "revoke", "role", "status", "disposition", "version", "features", "source"],
)
def test_changes_during_compute_rejected(
    platform, case_team, assessment_setup, monkeypatch, change
):
    service, request, _ = assessment_setup
    compute = service._compute

    def mutate(*args):
        result = compute(*args)
        with Session(platform[1]) as session, session.begin():
            case = session.get(Case, request["case_id"])
            if change == "reassign":
                case.assigned_to = UUID(case_team["users"]["analysttwo"])
                case.version += 1
            if change == "revoke":
                session.get(User, request["actor_id"]).active = False
            if change == "role":
                # A manager loses access when downgraded to an unassigned analyst.
                session.get(User, request["actor_id"]).role = "analyst"
            if change == "status":
                case.status = "closed"
            if change == "disposition":
                case.disposition = "recommend"
            if change == "version":
                case.version += 1
            if change in {"features", "source"}:
                alert = session.get(Alert, case.alert_id)
                if change == "source":
                    alert.source_id = "synthetic-modified-source"
                else:
                    from app.schemas.alerts import AlertIngestionInput
                    from app.services.ingestion import fingerprints

                    alert.features = {**alert.features, "income": 0}
                    alert.input_sha256 = fingerprints(
                        AlertIngestionInput(
                            source_id=alert.source_id,
                            data_classification="synthetic",
                            feature_contract_version=alert.feature_contract_version,
                            features=alert.features,
                        )
                    )[0]
        return result

    if change == "role":
        request = {**request, "actor_id": UUID(case_team["users"]["supervisor"])}
    monkeypatch.setattr(service, "_compute", mutate)
    with pytest.raises((AssessmentNotFound, AssessmentConflict)):
        service.assess(**request)
    assert counts(platform[1]) == [0] * 5


@pytest.mark.parametrize(
    "change", ["score", "shap", "identity", "method", "policy", "nan", "unverified", "extra"]
)
def test_inconsistent_result_rejected(platform, assessment_setup, monkeypatch, change):
    service, request, _ = assessment_setup
    compute = service._compute

    def corrupt(*args):
        result = copy.deepcopy(compute(*args))
        if change == "score":
            result["explanation"]["model_score"] += 0.01
        if change == "shap":
            result["explanation"]["encoded_contributions"] = (0.0,) * 41
        if change == "identity":
            result["score"]["model_sha256"] = "0" * 64
        if change == "method":
            result["explanation"]["method"]["positive_class_index"] = 0
        if change == "policy":
            result["policy"]["recommended_route"] = "review_reduction_candidate"
        if change == "nan":
            result["explanation"]["base_value"] = float("nan")
        if change == "unverified":
            result["explanation"]["status"] = "unavailable"
        if change == "extra":
            result["explanation"]["features"][0]["value"] = "private-value-marker"
        return result

    monkeypatch.setattr(service, "_compute", corrupt)
    with pytest.raises(AssessmentUnavailable, match="assessment_result_invalid"):
        service.assess(**request)
    assert counts(platform[1]) == [0] * 5


@pytest.mark.parametrize(
    "table", ["model_scores", "decisions", "assessment_explanations", "audit_events", "assessments"]
)
def test_write_failure_atomic_and_sanitized(platform, assessment_setup, table):
    service, request, _ = assessment_setup

    def reject(connection, cursor, statement, parameters, context, many):
        if statement.lower().startswith("insert into " + table):
            raise RuntimeError("private-feature-value-marker")

    event.listen(platform[1], "before_cursor_execute", reject)
    try:
        with pytest.raises(AssessmentUnavailable) as error:
            service.assess(**request)
        assert "private-feature-value-marker" not in str(error.value)
    finally:
        event.remove(platform[1], "before_cursor_execute", reject)
    assert counts(platform[1]) == [0] * 5
    assert service.assess(**request)[1]


@pytest.mark.parametrize(
    "table,column",
    [
        ("assessments", "status"),
        ("assessment_explanations", "payload"),
        ("model_scores", "model_version"),
        ("decisions", "mode"),
        ("audit_events", "action"),
    ],
)
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_database_immutability(platform, assessment_setup, table, column, operation):
    service, request, _ = assessment_setup
    service.assess(**request)
    sql = (
        f"UPDATE {table} SET {column} = {column}"
        if operation == "update"
        else f"DELETE FROM {table}"
    )
    # Restrict audit rows to the assessment event, leaving previous login/ingestion events alone.
    if table == "audit_events":
        sql += " WHERE action = 'assessment.completed'"
    with pytest.raises(DBAPIError, match="immutable_assessment_record"):
        with platform[1].begin() as connection:
            connection.execute(text(sql))
    assert counts(platform[1]) == [1] * 5


def test_preexisting_closed_and_invalid_input(platform, assessment_setup):
    service, request, calls = assessment_setup
    with Session(platform[1]) as session, session.begin():
        session.get(Case, request["case_id"]).status = "closed"
    with pytest.raises(AssessmentConflict):
        service.assess(**request)
    with Session(platform[1]) as session, session.begin():
        case = session.get(Case, request["case_id"])
        case.status = "open"
        session.get(Alert, case.alert_id).features = {"income": "private-malformed-marker"}
    with pytest.raises(AssessmentUnavailable, match="assessment_input_unavailable"):
        service.assess(**request)
    assert not calls


def test_reassignment_removes_assessment_history_access(platform, case_team, assessment_setup):
    service, request, _ = assessment_setup
    result, _ = service.assess(**request)
    with Session(platform[1]) as session, session.begin():
        case = session.get(Case, request["case_id"])
        case.assigned_to = UUID(case_team["users"]["analysttwo"])
        case.version += 1
    with pytest.raises(AssessmentNotFound):
        service.assess(**request)  # A receipt is never an authorization bypass.
    with pytest.raises(AssessmentNotFound):
        service.list(actor_id=request["actor_id"], case_id=request["case_id"])
    new_owner = UUID(case_team["users"]["analysttwo"])
    loaded = service.get(
        actor_id=new_owner, case_id=request["case_id"], assessment_id=UUID(result["assessment_id"])
    )
    assert loaded["actor_id"] == str(request["actor_id"])


def test_model_failure_sanitized_and_no_partial_state(platform, assessment_setup, monkeypatch):
    service, request, _ = assessment_setup

    def fail(*args):
        raise RuntimeError("private-model-feature-marker")

    monkeypatch.setattr(service, "_compute", fail)
    with pytest.raises(AssessmentUnavailable, match="assessment_processing_unavailable"):
        service.assess(**request)
    assert counts(platform[1]) == [0] * 5


def test_downgrade_refuses_assessment_history(platform, assessment_setup):
    from alembic.config import Config
    from conftest import BACKEND

    from alembic import command

    service, request, _ = assessment_setup
    result, _ = service.assess(**request)
    with pytest.raises(RuntimeError, match="Assessment history exists"):
        command.downgrade(Config(str(BACKEND / "alembic.ini")), "0003_case_security")
    assert service.get(
        actor_id=request["actor_id"],
        case_id=request["case_id"],
        assessment_id=UUID(result["assessment_id"]),
    )
