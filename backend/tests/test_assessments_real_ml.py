"""Opt-in PostgreSQL + actual pinned Linux RF/SHAP acceptance; no success mocks."""

import os
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, Case
from app.services.assessments import AssessmentService


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="Opt-in actual Linux ML/PostgreSQL acceptance",
)
@pytest.mark.parametrize("income", [None, 0])
def test_real_pipeline_assessment_persists_without_case_action(
    platform, case_team, alert_payload, income
):
    assert sys.platform == "linux" and platform[1].dialect.name == "postgresql"
    from trueflag_ml.scoring import RFScoringService

    service = AssessmentService(platform[1])
    alert_payload["source_id"] = "synthetic-real-ml-" + uuid4().hex
    alert_payload["features"]["income"] = income
    response = platform[0].post(
        "/api/v1/alerts",
        json=alert_payload,
        headers={**case_team["auth"]["admin"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    case_id = UUID(response.json()["case_id"])
    actor_id = UUID(case_team["users"]["admin"])
    run_id = uuid4()
    request = dict(
        actor_id=actor_id,
        case_id=case_id,
        expected_version=1,
        run_id=run_id,
        idempotency_key="actual-linux-assessment",
        policy="Coverage",
    )
    result, created = service.assess(**request)
    assert created and result["explanation"]["status"] == "verified"
    income_attribution = next(f for f in result["explanation"]["features"] if f["name"] == "income")
    assert income_attribution["missing"] is (income is None)
    assert result["verification"]["independent_model_and_root_checks"] is True
    with Session(platform[1]) as session:
        case = session.get(Case, case_id)
        features = session.get(Alert, case.alert_id).features
        assert case.status == "open" and case.version == 1 and case.disposition is None
    score = RFScoringService().score_one(str(case_id), features)
    assert score.score == result["score"]["score"] == result["explanation"]["model_score"]
    loaded = service.get(
        actor_id=actor_id, case_id=case_id, assessment_id=UUID(result["assessment_id"])
    )
    assert loaded["content_sha256"] == result["content_sha256"]
    assert service.assess(**request)[1] is False
    second, created = service.assess(
        **{**request, "run_id": uuid4(), "idempotency_key": "real-reassessment"}
    )
    assert created and second["version"] == 2
