"""HTTP/security/persistence acceptance; explicit synthetic producer, real ML tested separately."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_assessment_jobs import jobs as _jobs_fixture
from test_assessment_jobs import result_for
from test_assessments import assessment_setup as _assessment_fixture
from test_assessments import counts

from app.main import create_app
from app.models import AssessmentJob, AuditEvent, Case, User

jobs = _jobs_fixture
assessment_setup = _assessment_fixture
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def postgres(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("PostgreSQL assessment API acceptance")


@pytest.fixture
def api(platform, case_team, jobs):
    queue, token, request, producer, _ = jobs
    return dict(
        client=platform[0],
        engine=platform[1],
        settings=platform[2],
        team=case_team,
        queue=queue,
        token=token,
        request=request,
        producer=producer,
        body={
            "expected_version": request["expected_version"],
            "run_id": str(request["run_id"]),
            "policy": request["policy"],
        },
    )


def submit(api, *, body=None, key=None, case_id=None, actor="analyst"):
    return api["client"].post(
        f"/api/v1/cases/{case_id or api['request']['case_id']}/assessments",
        json=api["body"] if body is None else body,
        headers={
            **api["team"]["auth"][actor],
            "Idempotency-Key": key or api["request"]["idempotency_key"],
        },
    )


def finish(api):
    response = submit(api)
    assert response.status_code == 202
    claim = api["queue"].claim(api["token"])
    result = result_for(api["queue"], api["token"], claim, api["producer"])
    completed = api["queue"].complete(api["token"], claim, result)
    return response.json(), completed


def test_async_lifecycle_projection_history_and_audit(api):
    response = submit(api)
    assert response.status_code == 202 and response.json()["status"] == "pending"
    assert response.headers["location"] == "/api/v1/assessment-jobs/" + response.json()["job_id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "2" and counts(api["engine"]) == [0] * 5
    auth = api["team"]["auth"]["analyst"]
    claim = api["queue"].claim(api["token"])
    running = api["client"].get(response.headers["location"], headers=auth)
    assert running.status_code == 200 and running.json()["status"] == "running"
    api["queue"].complete(
        api["token"], claim, result_for(api["queue"], api["token"], claim, api["producer"])
    )
    job = api["client"].get(response.headers["location"], headers=auth).json()
    path = f"/api/v1/cases/{job['case_id']}/assessments"
    detail_response = api["client"].get(path + "/" + job["assessment_id"], headers=auth)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["score"] == 0.15 and detail["explanation"]["status"] == "verified"
    assert len(detail["explanation"]["features"]) == 27
    assert (
        abs(
            detail["explanation"]["base_value"]
            + sum(f["contribution"] for f in detail["explanation"]["features"])
            - detail["score"]
        )
        < 1e-6
    )
    assert detail["input_provenance"]["contract_sha256"]
    assert detail["policy_trace"]["override_reason"] == "coverage_high_priority_protection"
    assert detail["explanation"]["verification"]["runtime_dependencies"]
    for forbidden in [
        '"key_sha256"',
        '"request_sha256"',
        '"source_id"',
        '"snapshot"',
        '"encoded_contributions"',
        '"encoded_to_original"',
        '"worker_id"',
        '"lease_token"',
        '"kyc_risk_score"',
        '"value"',
    ]:
        assert forbidden not in detail_response.text
    page = api["client"].get(path + "?limit=1&offset=0", headers=auth)
    assert page.status_code == 200 and page.json()["total"] == 1
    assert "explanation" not in page.json()["items"][0]
    assert api["client"].get(path + "?offset=1", headers=auth).json()["items"] == []
    with Session(api["engine"]) as session:
        actions = list(session.scalars(select(AuditEvent.action)))
        assert "assessment.job.requested" in actions and "assessment.job.status_read" in actions
        assert "assessment.detail_read" in actions and "assessment.history_read" in actions
        case = session.get(Case, api["request"]["case_id"])
        assert case.status == "open" and case.version == 1 and case.disposition is None


def test_duplicate_and_reassessment_versions(api):
    first, completed = finish(api)
    again = submit(api)
    assert again.status_code == 202 and again.json() == completed
    assert first["job_id"] == completed["job_id"] and counts(api["engine"]) == [1] * 5
    response = submit(api, body={**api["body"], "run_id": str(uuid4())}, key="new-api-assessment")
    assert response.status_code == 202
    claim = api["queue"].claim(api["token"])
    api["queue"].complete(
        api["token"], claim, result_for(api["queue"], api["token"], claim, api["producer"])
    )
    path = f"/api/v1/cases/{api['request']['case_id']}/assessments"
    page = api["client"].get(path, headers=api["team"]["auth"]["analyst"]).json()
    assert page["total"] == 2 and [v["version"] for v in page["items"]] == [2, 1]


@pytest.mark.parametrize(
    "change,key",
    [({"policy": "Balanced"}, None), ({"run_id": str(uuid4())}, None), ({}, "changed-idempotency")],
)
def test_idempotency_conflicts(api, change, key):
    assert submit(api).status_code == 202
    response = submit(api, body={**api["body"], **change}, key=key)
    assert response.status_code == 409
    with Session(api["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"score": 0.99},
        {"features": {"income": "private-value-marker"}},
        {"actor_id": str(uuid4())},
        {"model_sha256": "0" * 64},
        {"expected_version": True},
        {"expected_version": 1.0},
        {"expected_version": 0},
        {"policy": "coverage"},
        {"run_id": "private-value-marker"},
    ],
)
def test_strict_request_body(api, change):
    response = submit(api, body={**api["body"], **change})
    assert response.status_code == 422 and "private-value-marker" not in response.text


@pytest.mark.parametrize("key", [None, "short", "invalid/key", "a" * 129])
def test_required_strict_key(api, key):
    headers = api["team"]["auth"]["analyst"].copy()
    if key is not None:
        headers["Idempotency-Key"] = key
    response = api["client"].post(
        f"/api/v1/cases/{api['request']['case_id']}/assessments", json=api["body"], headers=headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=51", "offset=-1", "offset=10001", "limit=true", "sort_by=score"]
)
def test_bounded_history_queries(api, query):
    path = f"/api/v1/cases/{api['request']['case_id']}/assessments?{query}"
    assert api["client"].get(path, headers=api["team"]["auth"]["analyst"]).status_code == 422


def test_anonymous_all_endpoints(api):
    case = api["request"]["case_id"]
    for path in [
        f"/api/v1/cases/{case}/assessments",
        f"/api/v1/cases/{case}/assessments/{uuid4()}",
        f"/api/v1/assessment-jobs/{uuid4()}",
    ]:
        assert api["client"].get(path).status_code == 401
    assert (
        api["client"]
        .post(
            f"/api/v1/cases/{case}/assessments",
            json=api["body"],
            headers={"Idempotency-Key": "anonymous-api-key"},
        )
        .status_code
        == 401
    )


def test_cross_analyst_and_cross_case_enumeration(api):
    _, completed = finish(api)
    job_path = "/api/v1/assessment-jobs/" + completed["job_id"]
    case = api["request"]["case_id"]
    paths = [
        job_path,
        f"/api/v1/cases/{case}/assessments",
        f"/api/v1/cases/{case}/assessments/{completed['assessment_id']}",
    ]
    auth = api["team"]["auth"]["analysttwo"]
    for path in paths:
        response = api["client"].get(path, headers=auth)
        assert response.status_code == 404 and response.json() == {
            "detail": "Assessment resource not found"
        }
    assert submit(api, actor="analysttwo").status_code == 404
    assert api["client"].get("/api/v1/assessment-jobs/" + str(uuid4()), headers=auth).json() == {
        "detail": "Assessment resource not found"
    }
    own_other = api["team"]["ids"][3]
    assert (
        api["client"]
        .get(
            f"/api/v1/cases/{own_other}/assessments/{completed['assessment_id']}",
            headers=api["team"]["auth"]["analyst"],
        )
        .status_code
        == 404
    )


@pytest.mark.parametrize("actor", ["admin", "supervisor"])
def test_workspace_manager_scope(api, actor):
    assert submit(api, actor=actor).status_code == 202
    path = f"/api/v1/cases/{api['request']['case_id']}/assessments"
    assert api["client"].get(path, headers=api["team"]["auth"][actor]).status_code == 200


def test_revocation_after_request_and_read(api):
    response = submit(api)
    claim = api["queue"].claim(api["token"])
    result = result_for(api["queue"], api["token"], claim, api["producer"])
    assignment = api["client"].put(
        f"/api/v1/cases/{api['request']['case_id']}/assignment",
        headers=api["team"]["auth"]["supervisor"],
        json={"assigned_to": api["team"]["users"]["analysttwo"], "expected_version": 1},
    )
    assert assignment.status_code == 200
    from app.services.assessments import AssessmentNotFound

    with pytest.raises(AssessmentNotFound):
        api["queue"].complete(api["token"], claim, result)
    api["queue"].fail(api["token"], claim, "authorization_changed", retryable=False)
    assert (
        api["client"]
        .get(response.headers["location"], headers=api["team"]["auth"]["analyst"])
        .status_code
        == 404
    )
    current = api["client"].get(
        response.headers["location"], headers=api["team"]["auth"]["analysttwo"]
    )
    assert current.status_code == 200 and current.json()["fallback_route"] == "manual_review"
    assert counts(api["engine"]) == [0] * 5


def test_active_role_checked_with_existing_jwt(api):
    response = submit(api, actor="supervisor")
    with Session(api["engine"]) as session, session.begin():
        session.get(User, UUID(api["team"]["users"]["supervisor"])).role = "analyst"
    assert (
        api["client"]
        .get(response.headers["location"], headers=api["team"]["auth"]["supervisor"])
        .status_code
        == 404
    )
    with Session(api["engine"]) as session, session.begin():
        session.get(User, UUID(api["team"]["users"]["analyst"])).active = False
    assert submit(api).status_code == 401


def test_queue_capacity_worker_downtime_and_retry(api):
    api["settings"].assessment_queue_capacity = 1
    first = submit(api)
    for _ in range(2):
        assert (
            api["client"]
            .get(first.headers["location"], headers=api["team"]["auth"]["analyst"])
            .json()["status"]
            == "pending"
        )
    full = submit(
        api,
        case_id=api["team"]["ids"][3],
        body={**api["body"], "run_id": str(uuid4())},
        key="full-queue-other-case",
    )
    assert full.status_code == 503 and full.headers["retry-after"] == "5"
    assert submit(api).status_code == 202
    assert counts(api["engine"]) == [0] * 5


def test_shared_request_budget_and_window_reset(api):
    api["settings"].assessment_api_rate_limit = 2
    first = submit(api)
    assert (
        api["client"]
        .get(first.headers["location"], headers=api["team"]["auth"]["analyst"])
        .status_code
        == 200
    )
    with TestClient(create_app(api["settings"], api["engine"])) as other:
        limited = other.get(first.headers["location"], headers=api["team"]["auth"]["analyst"])
        assert limited.status_code == 429 and 1 <= int(limited.headers["retry-after"]) <= 60
    assert (
        api["client"]
        .get(first.headers["location"], headers=api["team"]["auth"]["supervisor"])
        .status_code
        == 200
    )
    with api["engine"].begin() as connection:
        connection.execute(
            text(
                "UPDATE assessment_api_throttles SET window_start = clock_timestamp() - interval '61 seconds'"
            )
        )
    assert submit(api).status_code == 202


def test_concurrent_duplicate_submissions(api):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: submit(api), range(4)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["job_id"] for r in responses}) == 1
    with Session(api["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 1


def test_concurrent_capacity_cannot_overshoot(api):
    api["settings"].assessment_queue_capacity = 1

    def request(index):
        return submit(
            api,
            case_id=api["team"]["ids"][[0, 3][index]],
            body={**api["body"], "run_id": str(uuid4())},
            key=f"capacity-race-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, range(2)))
    assert sorted(r.status_code for r in results) == [202, 503]
    with Session(api["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 1


def test_terminal_failure_is_sanitized_without_case_action(api):
    response = submit(api)
    claim = api["queue"].claim(api["token"])
    api["queue"].fail(api["token"], claim, "private-error-marker", retryable=False)
    status = api["client"].get(response.headers["location"], headers=api["team"]["auth"]["analyst"])
    assert (
        status.json()["status"] == "failed" and status.json()["fallback_route"] == "manual_review"
    )
    assert "private-error-marker" not in status.text and counts(api["engine"]) == [0] * 5
    with Session(api["engine"]) as session:
        case = session.get(Case, api["request"]["case_id"])
        assert case.status == "open" and case.disposition is None


@pytest.mark.parametrize("action", ["assessment.job.requested", "assessment.history_read"])
def test_audit_failure_is_atomic_and_sanitized(api, action):
    with api["engine"].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_api_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-api-audit-marker'; END; $$"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER reject_api_audit BEFORE INSERT ON audit_events FOR EACH ROW WHEN (NEW.action = '{action}') EXECUTE FUNCTION reject_api_audit()"
            )
        )
    response = (
        submit(api)
        if action.endswith("requested")
        else api["client"].get(
            f"/api/v1/cases/{api['request']['case_id']}/assessments",
            headers=api["team"]["auth"]["analyst"],
        )
    )
    assert response.status_code == 503 and "private-api-audit-marker" not in response.text
    with Session(api["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
            )
            == 0
        )


@pytest.mark.parametrize("target", ["missing_result", "foreign_case"])
def test_failed_and_hidden_reads_cannot_bypass_budget(api, target):
    api["settings"].assessment_api_rate_limit = 1
    path = (
        f"/api/v1/cases/{api['request']['case_id']}/assessments/{uuid4()}"
        if target == "missing_result"
        else f"/api/v1/cases/{api['team']['ids'][1]}/assessments"
    )
    auth = api["team"]["auth"]["analyst"]
    assert api["client"].get(path, headers=auth).status_code == 404
    assert (
        api["client"]
        .get(f"/api/v1/cases/{api['request']['case_id']}/assessments", headers=auth)
        .status_code
        == 429
    )


def test_sensitive_read_audit_is_immutable(api):
    _, completed = finish(api)
    path = f"/api/v1/cases/{api['request']['case_id']}/assessments"
    auth = api["team"]["auth"]["analyst"]
    assert api["client"].get(path, headers=auth).status_code == 200
    assert (
        api["client"].get(path + "/" + completed["assessment_id"], headers=auth).status_code == 200
    )
    with pytest.raises(DBAPIError, match="immutable_job_audit"):
        with api["engine"].begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM audit_events WHERE action IN ('assessment.history_read','assessment.detail_read')"
                )
            )
