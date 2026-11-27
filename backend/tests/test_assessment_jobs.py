"""PG queue acceptance with explicit synthetic producers; real child tests are separate."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_assessments import assessment_setup as _assessment_fixture
from test_assessments import counts

from app.models import AssessmentJob, Case, User
from app.services.assessment_jobs import (
    AssessmentJobService,
    JobError,
    JobUnavailable,
    LeaseLost,
    WorkerDenied,
    WorkerLimits,
)
from app.services.assessments import AssessmentConflict, AssessmentNotFound

assessment_setup = _assessment_fixture
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def postgres_only(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("PostgreSQL durable queue acceptance")


@pytest.fixture
def jobs(platform, case_team, assessment_setup):
    service, request, _ = assessment_setup
    queue = AssessmentJobService(platform[1], limits=WorkerLimits(3, 20, 1))
    token = secrets.token_hex(32)
    identity = queue.register_worker(
        admin_id=UUID(case_team["users"]["admin"]), name="synthetic-worker", token=token
    )
    return queue, token, request, service, identity


def due(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE assessment_jobs SET available_at = clock_timestamp() - interval '1 second' WHERE status = 'pending'"
            )
        )


def expire(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE assessment_jobs SET lease_until = clock_timestamp() - interval '1 second' WHERE status = 'running'"
            )
        )


def result_for(queue, token, claim, producer):
    data = queue.prepare(token, claim)
    return producer._compute(data["actor_id"], data["case_id"], data["features"], data["policy"])


def test_enqueue_complete_retry_and_reassessment(platform, jobs):
    queue, token, request, producer, _ = jobs
    first, created = queue.enqueue(**request)
    assert created and first["status"] == "pending"
    assert queue.enqueue(**request) == (first, False)
    claim = queue.claim(token)
    result = result_for(queue, token, claim, producer)
    completed = queue.complete(token, claim, result)
    assert completed["status"] == "succeeded" and completed["attempts"] == 1
    assert counts(platform[1]) == [1] * 5
    with pytest.raises(LeaseLost):
        queue.complete(token, claim, result)
    assert queue.claim(token) is None and queue.enqueue(**request)[0] == completed
    other, _ = queue.enqueue(**{**request, "run_id": uuid4(), "idempotency_key": "second-job-run"})
    claim = queue.claim(token)
    queue.complete(token, claim, result_for(queue, token, claim, producer))
    assert other["job_id"] != completed["job_id"] and counts(platform[1]) == [2] * 5
    assert [
        r["version"]
        for r in producer.list(actor_id=request["actor_id"], case_id=request["case_id"])
    ] == [2, 1]
    with Session(platform[1]) as session:
        case = session.get(Case, request["case_id"])
        assert case.status == "open" and case.disposition is None and case.version == 1


def test_enqueue_reuses_existing_verified_run(platform, jobs):
    queue, _, request, producer, _ = jobs
    assessment, _ = producer.assess(**request)
    job, created = queue.enqueue(**request)
    assert (
        created
        and job["status"] == "succeeded"
        and job["assessment_id"] == assessment["assessment_id"]
    )
    assert counts(platform[1]) == [1] * 5


@pytest.mark.parametrize(
    "change", [{"policy": "Balanced"}, {"run_id": uuid4()}, {"idempotency_key": "another-job-key"}]
)
def test_enqueue_conflicts(jobs, change):
    queue, _, request, _, _ = jobs
    queue.enqueue(**request)
    with pytest.raises(AssessmentConflict):
        queue.enqueue(**{**request, **change})


def test_concurrent_enqueue_and_claim(platform, jobs):
    queue, token, request, _, _ = jobs
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: queue.enqueue(**request), range(4)))
    assert sum(created for _, created in results) == 1
    barrier = Barrier(4)

    def claim(_):
        barrier.wait(timeout=10)
        return queue.claim(token)

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim, range(4)))
    assert sum(c is not None for c in claims) == 1
    assert counts(platform[1]) == [0] * 5


def test_expired_lease_recovery_fences_old_worker(platform, jobs):
    queue, token, request, producer, _ = jobs
    queue.enqueue(**request)
    old = queue.claim(token)
    result = result_for(queue, token, old, producer)
    queue.heartbeat(token, old)
    expire(platform[1])
    assert queue.recover_expired(token) == 1
    assert queue.claim(token) is None  # Backoff is durable, not an in-memory sleep.
    due(platform[1])
    current = queue.claim(token)
    assert current.job_id == old.job_id and current.lease_token != old.lease_token
    for action in [
        lambda: queue.heartbeat(token, old),
        lambda: queue.complete(token, old, result),
        lambda: queue.fail(token, old, "child_failed"),
    ]:
        with pytest.raises(LeaseLost):
            action()
    assert queue.complete(token, current, result)["attempts"] == 2
    assert counts(platform[1]) == [1] * 5


def test_repeated_worker_crash_exhausts_to_manual_review(platform, jobs):
    queue, token, request, _, _ = jobs
    queued, _ = queue.enqueue(**request)
    for _ in range(3):
        assert queue.claim(token) is not None
        expire(platform[1])  # Simulate supervisor death with no acknowledgement.
        assert queue.recover_expired(token) == 1
        due(platform[1])
    result = queue.get(
        actor_id=request["actor_id"], case_id=request["case_id"], job_id=UUID(queued["job_id"])
    )
    assert result["status"] == "failed" and result["attempts"] == 3
    assert result["fallback_route"] == "manual_review" and result["human_decision_required"] is True
    assert queue.claim(token) is None and counts(platform[1]) == [0] * 5
    with Session(platform[1]) as session:
        case = session.get(Case, request["case_id"])
        assert case.status == "open" and case.disposition is None


def test_failure_backoff_and_sanitization(platform, jobs):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    claim = queue.claim(token)
    result = queue.fail(token, claim, "private-error-value")
    assert result["failure_code"] == "processing_unavailable" and result["status"] == "pending"
    assert queue.claim(token) is None
    with Session(platform[1]) as session:
        row = session.get(AssessmentJob, claim.job_id)
        now = session.scalar(select(func.clock_timestamp()))
        assert 0 < (row.available_at - now).total_seconds() <= 5


@pytest.mark.parametrize("fault", ["job_update", "success_audit"])
def test_completion_atomic_with_database_failure(platform, jobs, fault):
    queue, token, request, producer, _ = jobs
    queue.enqueue(**request)
    claim = queue.claim(token)
    result = result_for(queue, token, claim, producer)
    table = "assessment_jobs" if fault == "job_update" else "audit_events"
    action = "UPDATE" if fault == "job_update" else "INSERT"
    condition = (
        "NEW.status = 'succeeded'"
        if fault == "job_update"
        else "NEW.action = 'assessment.job.succeeded'"
    )
    with platform[1].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_job_completion() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-db-fault'; END; $$"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER reject_job_completion BEFORE {action} ON {table} FOR EACH ROW WHEN ({condition}) EXECUTE FUNCTION reject_job_completion()"
            )
        )
    with pytest.raises(JobUnavailable) as error:
        queue.complete(token, claim, result)
    assert str(error.value) == "job_database_unavailable" and counts(platform[1]) == [0] * 5
    with platform[1].begin() as connection:
        connection.execute(text(f"DROP TRIGGER reject_job_completion ON {table}"))
        connection.execute(text("DROP FUNCTION reject_job_completion()"))
    assert queue.complete(token, claim, result)["status"] == "succeeded"


@pytest.mark.parametrize("which", ["unknown", "malformed", "revoked"])
def test_service_permission_enforced(platform, case_team, jobs, which):
    queue, token, request, _, identity = jobs
    queue.enqueue(**request)
    if which == "revoked":
        queue.revoke_worker(admin_id=UUID(case_team["users"]["admin"]), worker_id=identity)
    else:
        token = secrets.token_hex(32) if which == "unknown" else "analyst-token"
    with pytest.raises(WorkerDenied):
        queue.claim(token)
    with pytest.raises(WorkerDenied):
        queue.recover_expired(token)


def test_only_admin_provisions_worker(case_team, jobs):
    queue, _, _, _, _ = jobs
    with pytest.raises(WorkerDenied):
        queue.register_worker(
            admin_id=UUID(case_team["users"]["supervisor"]),
            name="denied-worker",
            token=secrets.token_hex(32),
        )


def test_case_permissions_and_revocation(platform, case_team, jobs):
    queue, token, request, _, _ = jobs
    job, _ = queue.enqueue(**request)
    with pytest.raises(AssessmentNotFound):
        queue.enqueue(**{**request, "actor_id": UUID(case_team["users"]["analysttwo"])})
    with pytest.raises(AssessmentNotFound):
        queue.get(
            actor_id=UUID(case_team["users"]["analysttwo"]),
            case_id=request["case_id"],
            job_id=UUID(job["job_id"]),
        )
    claim = queue.claim(token)
    with Session(platform[1]) as session, session.begin():
        session.get(User, request["actor_id"]).active = False
    with pytest.raises(AssessmentNotFound):
        queue.prepare(token, claim)
    assert queue.fail(token, claim, "authorization_changed", retryable=False)["status"] == "failed"
    assert counts(platform[1]) == [0] * 5


@pytest.mark.parametrize("field", ["version", "assignment", "status", "disposition"])
def test_stale_state_rejected(platform, case_team, jobs, field):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    claim = queue.claim(token)
    with Session(platform[1]) as session, session.begin():
        case = session.get(Case, request["case_id"])
        if field == "version":
            case.version += 1
        if field == "assignment":
            case.assigned_to = UUID(case_team["users"]["analysttwo"])
        if field == "status":
            case.status = "closed"
        if field == "disposition":
            case.disposition = "recommend"
    with pytest.raises((AssessmentNotFound, AssessmentConflict)):
        queue.prepare(token, claim)


def test_forged_claim_denied(jobs):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    claim = queue.claim(token)
    with pytest.raises(LeaseLost):
        queue.heartbeat(token, replace(claim, lease_token=uuid4()))


@pytest.mark.parametrize("operation", ["envelope", "terminal", "delete", "audit", "truncate"])
def test_job_history_is_protected(platform, jobs, operation):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    claim = queue.claim(token)
    queue.fail(token, claim, "stale_case", retryable=False)
    statement = {
        "envelope": "UPDATE assessment_jobs SET policy = 'Balanced'",
        "terminal": "UPDATE assessment_jobs SET failure_code = 'changed'",
        "delete": "DELETE FROM assessment_jobs",
        "audit": "DELETE FROM audit_events WHERE action LIKE 'assessment.job.%'",
        "truncate": "TRUNCATE assessment_jobs CASCADE",
    }[operation]
    with pytest.raises(DBAPIError, match="immutable_job"):
        with platform[1].begin() as connection:
            connection.execute(text(statement))


@pytest.mark.parametrize("limits", [(True, 10, 1), (2, 10, 1), (30, 301, 1), (3, 10, 2)])
def test_worker_limits_reject_invalid_values(limits):
    with pytest.raises(JobError):
        WorkerLimits(*limits)


@pytest.mark.parametrize("transition", ["enqueued", "claimed"])
def test_queue_audit_failure_rolls_back_transition(platform, jobs, transition):
    queue, token, request, _, _ = jobs
    job = queue.enqueue(**request)[0] if transition == "claimed" else None
    with platform[1].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_queue_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-queue-marker'; END; $$"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER reject_queue_audit BEFORE INSERT ON audit_events FOR EACH ROW WHEN (NEW.action = 'assessment.job.{transition}') EXECUTE FUNCTION reject_queue_audit()"
            )
        )
    with pytest.raises(JobUnavailable, match="job_database_unavailable"):
        queue.claim(token) if transition == "claimed" else queue.enqueue(**request)
    with Session(platform[1]) as session:
        rows = session.scalars(select(AssessmentJob)).all()
        assert len(rows) == (1 if job else 0)
        if rows:
            assert rows[0].status == "pending" and rows[0].attempts == 0
    with platform[1].begin() as connection:
        connection.execute(text("DROP TRIGGER reject_queue_audit ON audit_events"))
        connection.execute(text("DROP FUNCTION reject_queue_audit()"))
    if not job:
        queue.enqueue(**request)
    assert queue.claim(token) is not None and counts(platform[1]) == [0] * 5


def test_database_requires_manual_review_for_failed_job(platform, jobs):
    queue, _, request, _, _ = jobs
    job, _ = queue.enqueue(**request)
    with pytest.raises(DBAPIError, match="ck_job_state"):
        with platform[1].begin() as connection:
            connection.execute(
                text(
                    "UPDATE assessment_jobs SET status = 'failed', failure_code = 'child_failed', fallback_route = NULL"
                )
            )
    assert (
        queue.get(
            actor_id=request["actor_id"], case_id=request["case_id"], job_id=UUID(job["job_id"])
        )["status"]
        == "pending"
    )
