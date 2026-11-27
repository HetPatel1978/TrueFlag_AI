"""Redacted workbench projections and scoped server-side searches."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, AuditEvent, Case, User


def test_overview_auth_scope_redaction_and_audit(platform, case_team):
    client, engine, _, _ = platform
    path = f"/api/v1/cases/{case_team['ids'][0]}/overview"
    assert client.get(path).status_code == 401
    response = client.get(path, headers=case_team["auth"]["analyst"])
    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == "High" and body["assessment_status"] == "not_requested"
    assert body["latest_job_id"] is None
    assert not {"features", "snapshot", "password_hash", "kycRiskScore", "income"} & set(body)
    for actor in ["admin", "supervisor"]:
        assert client.get(path, headers=case_team["auth"][actor]).status_code == 200
    hidden = client.get(path, headers=case_team["auth"]["analysttwo"])
    missing = client.get(
        f"/api/v1/cases/{uuid4()}/overview", headers=case_team["auth"]["analysttwo"]
    )
    assert hidden.status_code == missing.status_code == 404 and hidden.json() == missing.json()
    assert response.headers["cache-control"] == "no-store"
    with Session(engine) as session:
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "case.overview_read"))


def test_literal_search_scoping_filters_and_priority_mapping(platform, case_team):
    client, engine, _, _ = platform
    with Session(engine) as session, session.begin():
        case = session.get(Case, UUID(case_team["ids"][0]))
        alert = session.get(Alert, case.alert_id)
        alert.features = {**alert.features, "kycRiskScore": 2}
    auth = case_team["auth"]["analyst"]

    def page(query):
        response = client.get("/api/v1/cases?" + query, headers=auth)
        assert response.status_code == 200
        return response.json()

    assert page("search=phase1-synthetic-0")["total"] == 1
    assert page("search=phase1-synthetic-1")["total"] == 0
    assert page("search=%25")["total"] == 0
    assert page("search=_")["total"] == 0
    assert page("priority=Standard")["items"][0]["id"] == case_team["ids"][0]
    assert page("priority=High&assessment_status=not_requested")["total"] == 1
    assert page("search=" + case_team["ids"][0])["total"] == 1
    assert page("assessment_status=succeeded")["total"] == 0


@pytest.mark.parametrize(
    "query", ["priority=Critical", "assessment_status=completed", "search=" + "x" * 129]
)
def test_invalid_workbench_filters(platform, case_team, query):
    assert (
        platform[0].get("/api/v1/cases?" + query, headers=case_team["auth"]["analyst"]).status_code
        == 422
    )


def test_revocation_removes_workbench_metadata(platform, case_team):
    client, engine, _, _ = platform
    with Session(engine) as session, session.begin():
        session.get(Case, UUID(case_team["ids"][0])).assigned_to = UUID(
            case_team["users"]["analysttwo"]
        )
    assert (
        client.get(
            f"/api/v1/cases/{case_team['ids'][0]}/overview", headers=case_team["auth"]["analyst"]
        ).status_code
        == 404
    )
    with Session(engine) as session, session.begin():
        session.get(User, UUID(case_team["users"]["supervisor"])).active = False
    assert client.get("/api/v1/cases", headers=case_team["auth"]["supervisor"]).status_code == 401
