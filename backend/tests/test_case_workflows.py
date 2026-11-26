"""Real PostgreSQL scope, safe projections, existing assignment CAS and audit membership."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_foundation import headers
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import request as investigation_request

from app.models import AuditEvent, User
from app.services.assessment_jobs import AssessmentJobService

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture


@pytest.mark.parametrize("retryable", [True, False])
def test_history_uses_actual_recorded_attempt_outcome_not_current_job_state(env, retryable):
    service = env["service"]
    service.request(
        env["users"]["admin"], env["case"], "history-attempt-001", investigation_request(env)
    )
    claim = service.claim(env["token"])
    service.fail(env["token"], claim, "processing_unavailable", retryable=retryable)
    c = env["platform"][0]
    result = c.get(f"/api/v1/cases/{env['case']}/activity", headers=headers(env["platform"]))
    assert result.status_code == 200
    events = {row["event_type"]: row for row in result.json()["items"]}
    assert events["summary_requested"]["outcome"] == "pending"
    assert events["summary_processing"]["outcome"] == "running"
    assert events["summary_attempt_failed"]["outcome"] == (
        "retry_scheduled" if retryable else "failed"
    )
    assert all(
        k not in result.text for k in ["worker_id", "manifest", "processing_unavailable", "run_id"]
    )


def test_history_records_real_published_summary_without_returning_its_packet(env):
    service = env["service"]
    service.request(
        env["users"]["admin"], env["case"], "history-published-001", investigation_request(env)
    )
    assert service.run_once(env["token"])["status"] == "succeeded"
    result = env["platform"][0].get(
        f"/api/v1/cases/{env['case']}/activity", headers=headers(env["platform"])
    )
    assert result.status_code == 200
    assert (
        next(i for i in result.json()["items"] if i["event_type"] == "summary_published")["outcome"]
        == "completed"
    )
    assert "transactions" not in result.text and "packet_sha256" not in result.text


@pytest.mark.parametrize(
    "name,count", [("analyst", 2), ("analysttwo", 1), ("supervisor", 4), ("admin", 4)]
)
def test_scoped_queue_has_names_no_raw_features(platform, case_team, name, count):
    response = platform[0].get("/api/v1/case-queue?limit=1", headers=case_team["auth"][name])
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == count and len(page["items"]) == 1
    assert page["items"][0]["assigned_investigator"] in {None, "analyst", "analysttwo"}
    assert page["items"][0]["review_recommendation"] is None
    assert all(s not in response.text for s in ["features", "password", "input_sha256", "1001"])


@pytest.mark.parametrize(
    "queue,name,count",
    [
        ("my", "analyst", 2),
        ("my", "supervisor", 0),
        ("unassigned", "admin", 1),
        ("review", "admin", 1),
        ("processing", "admin", 0),
    ],
)
def test_queues_use_only_recorded_case_and_assessment_states(
    platform, case_team, queue, name, count
):
    r = platform[0].get("/api/v1/case-queue?queue=" + queue, headers=case_team["auth"][name])
    assert r.status_code == 200 and r.json()["total"] == count


def test_search_counts_pagination_and_unassigned_queue_do_not_enumerate(platform, case_team):
    c = platform[0]
    h = case_team["auth"]["analyst"]
    assert c.get("/api/v1/case-queue?queue=unassigned", headers=h).status_code == 403
    assert c.get("/api/v1/cases?queue=unassigned", headers=h).status_code == 403
    for search in [case_team["ids"][1], case_team["ids"][2], "%", "_"]:
        r = c.get(
            "/api/v1/case-queue", params={"search": search, "limit": 1, "offset": 1}, headers=h
        )
        assert r.status_code == 200 and r.json()["total"] == 0 and r.json()["items"] == []
    assert c.get("/api/v1/case-queue").status_code == 401


def test_directory_is_manager_case_scoped_active_and_allowlisted(platform, case_team):
    c = platform[0]
    path = f"/api/v1/cases/{case_team['ids'][0]}/assignment-options"
    assert c.get(path, headers=case_team["auth"]["analyst"]).status_code == 403
    r = c.get(path, headers=case_team["auth"]["supervisor"])
    assert r.status_code == 200 and r.json()["total"] == 2
    assert all(set(i) == {"id", "username"} for i in r.json()["items"])
    assert {i["username"] for i in r.json()["items"]} == {"analyst", "analysttwo"}
    assert (
        c.get(path, params={"search": "%"}, headers=case_team["auth"]["admin"]).json()["total"] == 0
    )
    assert c.get(path + "?limit=21", headers=case_team["auth"]["admin"]).status_code == 422
    assert (
        c.get(
            path.replace(case_team["ids"][0], str(uuid4())), headers=case_team["auth"]["supervisor"]
        ).status_code
        == 404
    )


def test_workflow_overview_reuses_case_scope_and_projection(platform, case_team):
    c = platform[0]
    path = f"/api/v1/cases/{case_team['ids'][0]}/workflow"
    response = c.get(path, headers=case_team["auth"]["analyst"])
    assert response.status_code == 200
    assert response.json()["assigned_investigator"] == "analyst"
    assert "features" not in response.text
    assert c.get(path, headers=case_team["auth"]["analysttwo"]).status_code == 404
    assert c.get(path).status_code == 401


def test_role_revocation_rechecked_inside_workflow_service(platform, case_team, monkeypatch):
    from app.services.case_workflows import CaseWorkflowService

    original = CaseWorkflowService.directory

    def revoked(service, actor, *args):
        with Session(platform[1]) as s, s.begin():
            s.get(User, actor).active = False
        return original(service, actor, *args)

    monkeypatch.setattr(CaseWorkflowService, "directory", revoked)
    r = platform[0].get(
        f"/api/v1/cases/{case_team['ids'][0]}/assignment-options",
        headers=case_team["auth"]["admin"],
    )
    assert r.status_code == 403


def test_activity_redacts_payloads_and_binds_job_resources_not_json_claims(platform, case_team):
    c, e = platform[:2]
    target = UUID(case_team["ids"][0])
    foreign = UUID(case_team["ids"][1])
    job, _ = AssessmentJobService(e).enqueue(
        actor_id=UUID(case_team["users"]["admin"]),
        case_id=foreign,
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="foreign-history-job",
        policy="Coverage",
    )
    with Session(e) as s, s.begin():
        s.add_all(
            [
                AuditEvent(
                    action="evidence.source_revoked",
                    actor_id=UUID(case_team["users"]["admin"]),
                    resource_id=str(target),
                    details={
                        "source_id": str(uuid4()),
                        "private_notes": "private-marker",
                        "access_revision": 3,
                        "evidence_revision": True,
                    },
                ),
                AuditEvent(
                    action="assessment.job.failed",
                    resource_id=job["job_id"],
                    details={"case_id": str(target), "private_notes": "foreign-marker"},
                ),
                AuditEvent(
                    action="unknown.private_action",
                    resource_id=str(target),
                    details={"password": "private-marker"},
                ),
            ]
        )
    path = f"/api/v1/cases/{target}/activity"
    r = c.get(path, headers=case_team["auth"]["analyst"])
    assert r.status_code == 200
    rows = r.json()["items"]
    assert {i["event_type"] for i in rows} == {"alert_ingested", "evidence_access_revoked"}
    assert all(i["historical"] and i["actor"] == "redacted" for i in rows)
    assert all(i["case_id"] == str(target) for i in rows)
    assert all(
        x not in r.text
        for x in [
            "private-marker",
            "foreign-marker",
            "source_id",
            "actor_id",
            "worker",
            "manifest",
            "details",
            "password",
        ]
    )
    assert (
        next(i for i in rows if i["event_type"] == "evidence_access_revoked")["evidence_revision"]
        is None
    )
    assert c.get(path, headers=case_team["auth"]["analysttwo"]).status_code == 404
    assert c.get(path).status_code == 401


def test_concurrent_assignment_one_winner_history_and_stale_replay(platform, case_team):
    c = platform[0]
    case_id = case_team["ids"][2]
    h = case_team["auth"]["supervisor"]
    path = f"/api/v1/cases/{case_id}"

    def change(name):
        return c.put(
            path + "/assignment",
            headers=h,
            json={"expected_version": 1, "assigned_to": case_team["users"][name]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(change, ["analyst", "analysttwo"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert change("analyst").status_code == 409
    history = c.get(path + "/activity?category=assignment", headers=h)
    assert history.status_code == 200 and history.json()["total"] == 1
    assert history.json()["items"][0]["case_version"] == 2
    assert history.json()["items"][0]["assignment_change"] == "assigned"


def test_assignment_revocation_activity_and_deactivated_user_denied(platform, case_team):
    c, e = platform[:2]
    path = f"/api/v1/cases/{case_team['ids'][0]}"
    assert (
        c.put(
            path + "/assignment",
            headers=case_team["auth"]["admin"],
            json={"expected_version": 1, "assigned_to": None},
        ).status_code
        == 200
    )
    assert c.get(path + "/activity", headers=case_team["auth"]["analyst"]).status_code == 404
    with Session(e) as s, s.begin():
        s.get(User, UUID(case_team["users"]["analysttwo"])).active = False
    assert c.get("/api/v1/case-queue", headers=case_team["auth"]["analysttwo"]).status_code == 401


def test_history_pagination_unknown_fields_and_read_audit_rollback(platform, case_team):
    c, e = platform[:2]
    path = f"/api/v1/cases/{case_team['ids'][0]}/activity"
    h = case_team["auth"]["analyst"]
    assert c.get(path + "?limit=51", headers=h).status_code == 422
    assert c.get(path + "?raw=true", headers=h).status_code == 422
    r = c.get(path + "?limit=1&offset=1", headers=h)
    assert r.status_code == 200 and r.json()["total"] == 1 and r.json()["items"] == []

    def count():
        with Session(e) as s:
            return s.scalar(select(func.count()).select_from(AuditEvent))

    before = count()

    def fault(connection, cursor, statement, *args):
        if statement.lstrip().upper().startswith("INSERT INTO") and "audit_events" in statement:
            raise RuntimeError("private-marker")

    event.listen(e, "before_cursor_execute", fault)
    try:
        assert c.get(path, headers=h).status_code == 503
    finally:
        event.remove(e, "before_cursor_execute", fault)
    assert count() == before


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="Actual pinned model runtime required",
)
def test_queue_recommendation_and_activity_come_from_actual_immutable_assessment(
    platform, case_team
):
    from app.services.assessments import AssessmentService

    case_id = UUID(case_team["ids"][0])
    actor = UUID(case_team["users"]["admin"])
    record, _ = AssessmentService(platform[1]).assess(
        actor_id=actor,
        case_id=case_id,
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="workflow-actual-assessment",
        policy="Coverage",
    )
    r = platform[0].get(
        "/api/v1/case-queue", params={"search": str(case_id)}, headers=case_team["auth"]["analyst"]
    )
    assert (
        r.status_code == 200
        and r.json()["items"][0]["review_recommendation"] == record["decision"]["route"]
    )
    item = r.json()["items"][0]
    # Display fields: the verified score and the newest Activity History event.
    assert item["assessment_score"] == record["score"]["score"]
    assert 0 <= item["assessment_score"] <= 1
    r = platform[0].get(f"/api/v1/cases/{case_id}/activity", headers=case_team["auth"]["analyst"])
    row = next(i for i in r.json()["items"] if i["event_type"] == "assessment_completed")
    assert row["assessment_version"] == 1 and row["outcome"] == "completed"
    newest = max(datetime.fromisoformat(i["recorded_at"]) for i in r.json()["items"])
    assert datetime.fromisoformat(item["last_activity_at"]) == newest


def test_updated_time_counts_only_activity_history_events_of_the_case(platform, case_team):
    c, e = platform[:2]
    target, other = case_team["ids"][0], case_team["ids"][1]
    h = case_team["auth"]["supervisor"]

    def updated(case_id):
        r = c.get("/api/v1/case-queue", params={"search": case_id}, headers=h)
        return r.json()["items"][0]["last_activity_at"]

    before = updated(target)
    assert before is not None  # alert ingestion is an Activity History event
    with Session(e) as s, s.begin():
        # Not shown in Activity History (unknown action), or belongs to another case.
        s.add(AuditEvent(action="unknown.private_action", resource_id=target, details={}))
        s.add(AuditEvent(action="case.assignment_changed", resource_id=other, details={}))
    assert updated(target) == before
    with Session(e) as s, s.begin():
        s.add(AuditEvent(action="evidence.casework.note", resource_id=target, details={}))
    assert updated(target) > before
    single = c.get(f"/api/v1/cases/{target}/workflow", headers=h).json()
    assert single["last_activity_at"] == updated(target)
