"""Durable batch metadata/queue tests; actual RF+SHAP success tests are Linux-only below."""

import json
import os
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import test_csv_imports
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_csv_imports import approve, finish, prepare, total
from test_foundation import headers

from app.models import (
    Alert,
    Assessment,
    AssessmentJob,
    BatchAssessment,
    BatchAssessmentItem,
    BatchAssessmentRequest,
    Case,
    User,
)
from app.services.assessment_jobs import AssessmentJobService, WorkerDenied, WorkerLimits
from app.services.assessments import AssessmentNotFound, AssessmentService, AssessmentUnavailable
from app.services.batch_assessments import BatchAssessmentService

import_fixture = test_csv_imports.imports
base_upload = test_csv_imports.base_upload


@pytest.fixture
def batch_env(import_fixture):
    env = import_fixture
    env["settings"].batch_assessment_group_size = 2
    env["batch"] = BatchAssessmentService(env["engine"], env["settings"])
    env["ml"] = AssessmentJobService(env["engine"], limits=WorkerLimits(30, 120, 5))
    env["ml_token"] = secrets.token_hex(32)
    env["ml"].register_worker(
        admin_id=env["actor_id"], name="batch-ml-test-worker", token=env["ml_token"]
    )
    return env


def imported(env, rows=None):
    response = approve(env, prepare(env, [{}, {"income": "0"}] if rows is None else rows))
    assert response.status_code == 202, response.text
    finish(env)
    return env["client"].get(response.headers["location"], headers=env["auth"]).json()


def start(env, source=None, *, key=None, body=None, auth=None, policy="Balanced"):
    source = source or imported(env)
    request = {
        "start_assessment": True,
        "import_validation_sha256": source["validation_sha256"],
        "policy": policy,
    }
    return env["client"].post(
        "/api/v1/batch-imports/" + source["import_id"] + "/assessments",
        json=request if body is None else body,
        headers={
            **(env["auth"] if auth is None else auth),
            "Idempotency-Key": key or "batch-assessment-" + uuid4().hex,
        },
    )


def due(env, batch_id):
    with Session(env["engine"]) as session, session.begin():
        row = session.get(BatchAssessment, UUID(str(batch_id)))
        if row.status == "active":
            row.available_at = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)


def advance(env, batch_id):
    due(env, batch_id)
    return env["batch"].advance(UUID(str(batch_id)))


def fail_all(env):
    while claim := env["ml"].claim(env["ml_token"]):
        env["ml"].fail(env["ml_token"], claim, "child_failed", retryable=False)


def test_explicit_start_no_automatic_jobs_and_alias_idempotency(batch_env):
    env = batch_env
    source = imported(env)
    assert total(env, AssessmentJob) == total(env, BatchAssessment) == 0
    first = start(env, source, key="fixed-batch-request-key-001")
    assert first.status_code == 202, first.text
    value = first.json()
    assert (value["total_cases"], value["total_eligible_cases"], value["pending_dispatch"]) == (
        2,
        2,
        2,
    )
    assert total(env, AssessmentJob) == 0
    for key in ("fixed-batch-request-key-001", "different-key-same-batch-001"):
        replay = start(env, source, key=key)
        assert replay.status_code == 202 and replay.json()["batch_id"] == value["batch_id"]
    assert total(env, BatchAssessment) == 1 and total(env, BatchAssessmentRequest) == 2
    conflict = start(env, source, key="fixed-batch-request-key-001", policy="Coverage")
    assert conflict.status_code == 409
    assert advance(env, value["batch_id"]).queued == 2
    assert total(env, AssessmentJob) == 2
    fail_all(env)
    done = env["client"].get(first.headers["location"], headers=env["auth"]).json()
    assert done["status"] == "failed" and done["failed_manual_review"] == 2
    assert (
        start(env, source).json()["batch_id"] == value["batch_id"]
        and total(env, AssessmentJob) == 2
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_assessment", False),
        ("start_assessment", 1),
        ("start_assessment", "true"),
        ("policy", "Unsupported"),
        ("import_validation_sha256", "bad"),
    ],
)
def test_invalid_start_contract(batch_env, field, value):
    source = imported(batch_env)
    body = {
        "start_assessment": True,
        "import_validation_sha256": source["validation_sha256"],
        "policy": "Balanced",
    }
    body[field] = value
    assert start(batch_env, source, body=body).status_code == 422
    assert total(batch_env, BatchAssessment) == total(batch_env, AssessmentJob) == 0


def test_import_must_be_terminal_and_identity_match(batch_env):
    env = batch_env
    approved = approve(env, prepare(env, [{}]))
    source = approved.json()
    assert start(env, source).status_code == 409
    finish(env)
    source = env["client"].get(approved.headers["location"], headers=env["auth"]).json()
    assert (
        start(
            env,
            source,
            body={
                "start_assessment": True,
                "import_validation_sha256": "0" * 64,
                "policy": "Balanced",
            },
        ).status_code
        == 409
    )
    assert total(env, AssessmentJob) == 0


def test_only_success_rows_from_partial_import_and_closed_skips(batch_env):
    env = batch_env
    source = imported(env, [{}, {"income": "bad"}, {"income": "0"}])
    assert source["status"] == "partially_completed"
    with Session(env["engine"]) as session, session.begin():
        case = session.scalar(select(Case).order_by(Case.id))
        case.status = "closed"
        case.version += 1
    first = start(env, source)
    assert first.status_code == 202
    assert (
        first.json()["total_cases"] == 2
        and first.json()["total_eligible_cases"] == 1
        and first.json()["skipped"] == 1
    )
    assert advance(env, first.json()["batch_id"]).queued == 1
    assert total(env, AssessmentJob) == 1


def test_group_size_queue_capacity_and_dynamic_counters(batch_env):
    env = batch_env
    env["settings"].assessment_queue_capacity = 1
    source = imported(env, [{}, {}, {}, {}])
    first = start(env, source)
    bid = first.json()["batch_id"]
    progress = advance(env, bid)
    assert (progress.queued, progress.pending_dispatch, progress.backpressure_count) == (1, 3, 1)
    assert progress.reason_code == "queue_capacity" and total(env, AssessmentJob) == 1
    claim = env["ml"].claim(env["ml_token"])
    running = env["batch"].get(env["actor_id"], UUID(bid))
    assert running.running == 1 and running.queued == 0
    env["ml"].fail(env["ml_token"], claim, "child_failed", retryable=True)
    retry = env["batch"].get(env["actor_id"], UUID(bid))
    assert retry.queued == retry.retrying == 1 and retry.failed_manual_review == 0
    with Session(env["engine"]) as session, session.begin():
        session.get(AssessmentJob, claim.job_id).available_at = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(seconds=1)
    claim = env["ml"].claim(env["ml_token"])
    env["ml"].fail(env["ml_token"], claim, "child_failed", retryable=False)
    assert advance(env, bid).failed_manual_review == 1
    assert total(env, AssessmentJob) == 2
    # An idle SKIP LOCKED/due-time poll is not proof of a drained durable queue.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        fail_all(env)
        progress = advance(env, bid)
        if progress.status == "failed":
            break
        time.sleep(0.02)
    assert progress.failed_manual_review == 4 and progress.status == "failed"
    assert total(env, AssessmentJob) == 4
    with Session(env["engine"]) as session:
        assert all(
            c.status == "open" and c.disposition is None for c in session.scalars(select(Case))
        )


def test_existing_pending_job_is_adopted_without_new_job(batch_env):
    env = batch_env
    source = imported(env, [{}])
    with Session(env["engine"]) as session:
        case = session.scalar(select(Case))
        cid, version = case.id, case.version
    job, _ = env["ml"].enqueue(
        actor_id=env["actor_id"],
        case_id=cid,
        expected_version=version,
        run_id=uuid4(),
        idempotency_key="direct-before-batch-key",
        policy="Balanced",
    )
    first = start(env, source)
    progress = advance(env, first.json()["batch_id"])
    assert progress.queued == 1 and total(env, AssessmentJob) == 1
    with Session(env["engine"]) as session:
        item = session.scalar(select(BatchAssessmentItem))
        assert not item.originated and str(item.job_id) == job["job_id"]


def test_case_change_before_dispatch_is_skipped(batch_env):
    env = batch_env
    first = start(env, imported(env, [{}]))
    with Session(env["engine"]) as session, session.begin():
        case = session.scalar(select(Case))
        case.assigned_to = env["actor_id"]
        case.version += 1
    value = advance(env, first.json()["batch_id"])
    assert value.skipped == 1 and value.status == "completed" and total(env, AssessmentJob) == 0
    page = env["client"].get(first.headers["location"] + "/results", headers=env["auth"]).json()
    assert page["items"][0]["reason_code"] == "case_changed"


def test_cross_user_and_role_revocation_block_dispatch_and_worker(batch_env, platform):
    env = batch_env
    source = imported(env, [{}, {}, {}])
    first = start(env, source)
    analyst = headers(platform, "analyst")
    assert (
        start(env, source, auth={}).status_code == 401
        and start(env, source, auth=analyst).status_code == 403
    )
    with Session(env["engine"]) as session, session.begin():
        owner = session.get(User, env["actor_id"])
        session.add(
            User(username="otherbatchadmin", role="admin", password_hash=owner.password_hash)
        )
    other = headers(platform, "otherbatchadmin")
    assert start(env, source, auth=other).status_code == 404
    for suffix in ("", "/results"):
        assert (
            env["client"].get(first.headers["location"] + suffix, headers=other).status_code == 404
        )
        assert env["client"].get(first.headers["location"] + suffix).status_code == 401
        assert (
            env["client"].get(first.headers["location"] + suffix, headers=analyst).status_code
            == 403
        )
    advance(env, first.json()["batch_id"])
    claim = env["ml"].claim(env["ml_token"])
    with Session(env["engine"]) as session, session.begin():
        session.get(User, env["actor_id"]).role = "supervisor"
    # Supervisor still has ordinary workspace case scope, but no bulk execution authority.
    with pytest.raises(AssessmentNotFound):
        env["ml"].prepare(env["ml_token"], claim)
    env["ml"].fail(env["ml_token"], claim, "authorization_changed", retryable=False)
    assert advance(env, first.json()["batch_id"]).status == "stopped"
    assert env["client"].get(first.headers["location"], headers=env["auth"]).status_code == 403
    assert total(env, Assessment) == 0


def test_authorization_recheck_on_case_results_and_start(batch_env, monkeypatch):
    from sqlalchemy import false

    import app.services.batch_assessments as module

    env = batch_env
    source = imported(env, [{}])
    first = start(env, source)
    monkeypatch.setattr(module, "visible_cases", lambda user: false())
    assert env["client"].get(first.headers["location"], headers=env["auth"]).status_code == 404
    assert (
        env["client"].get(first.headers["location"] + "/results", headers=env["auth"]).status_code
        == 404
    )


def test_concurrent_requests_and_dispatch_are_idempotent(batch_env):
    env = batch_env
    source = imported(env, [{}, {}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(lambda _: start(env, source, key="concurrent-batch-key-001"), range(2))
        )
    assert [r.status_code for r in replies] == [202, 202]
    bid = replies[0].json()["batch_id"]
    assert replies[1].json()["batch_id"] == bid
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: env["batch"].advance(UUID(bid)), range(2)))
    assert total(env, AssessmentJob) == 2 and total(env, BatchAssessment) == 1


def test_shared_rate_limit_and_batch_capacity(batch_env):
    env = batch_env
    source = imported(env, [{}, {}, {}])
    env["settings"].assessment_api_rate_limit = 2
    first = start(env, source)
    result = advance(env, first.json()["batch_id"])
    assert (
        result.queued == 1 and result.pending_dispatch == 2 and result.reason_code == "rate_limit"
    )
    assert env["client"].get(first.headers["location"], headers=env["auth"]).status_code == 429
    env["settings"].assessment_api_rate_limit = 120
    env["settings"].batch_assessment_actor_capacity = 1
    assert start(env, source, policy="Coverage").status_code == 429
    assert start(env, source).status_code == 202


def test_atomic_group_rollback_after_queue_writes(batch_env):
    env = batch_env
    first = start(env, imported(env, [{}, {}]))
    bid = UUID(first.json()["batch_id"])
    with env["engine"].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_batch_link() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.status='job' THEN RAISE EXCEPTION 'private-link-failure'; END IF; RETURN NEW; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER reject_batch_link BEFORE UPDATE ON batch_assessment_items FOR EACH ROW EXECUTE FUNCTION reject_batch_link()"
            )
        )
    with pytest.raises(AssessmentUnavailable):
        env["batch"].advance(bid)
    assert total(env, AssessmentJob) == 0
    with env["engine"].begin() as connection:
        connection.execute(text("DROP TRIGGER reject_batch_link ON batch_assessment_items"))
    assert env["batch"].advance(bid).queued == 2


def test_progress_pagination_retry_failure_and_no_customer_values(batch_env, caplog):
    env = batch_env
    first = start(env, imported(env, [{}, {}, {}]))
    bid = first.json()["batch_id"]
    advance(env, bid)
    fail_all(env)
    advance(env, bid)
    fail_all(env)
    status = env["client"].get(first.headers["location"], headers=env["auth"])
    assert status.json()["failed_manual_review"] == 3
    results = env["client"].get(
        first.headers["location"] + "/results?offset=1&limit=1", headers=env["auth"]
    )
    value = results.json()
    assert (
        value["total"] == 3
        and len(value["items"]) == 1
        and value["items"][0]["source_row_number"] == 3
    )
    assert (
        value["items"][0]["outcome"] == "failed_manual_review" and not value["items"][0]["retrying"]
    )
    for query in ("?limit=26", "?offset=-1", "?offset=10001"):
        assert (
            env["client"]
            .get(first.headers["location"] + "/results" + query, headers=env["auth"])
            .status_code
            == 422
        )
    assert "preview-synthetic-" not in status.text + results.text + caplog.text


def test_original_worker_registry_still_required(batch_env):
    with pytest.raises(WorkerDenied):
        batch_env["ml"].claim(batch_env["token"])


def test_approved_batch_and_membership_integrity(batch_env):
    env = batch_env
    first = start(env, imported(env, [{}]))
    bid = UUID(first.json()["batch_id"])
    with Session(env["engine"]) as session:
        with pytest.raises(SQLAlchemyError):
            session.get(BatchAssessment, bid).policy = "Coverage"
            session.commit()
    advance(env, bid)
    with Session(env["engine"]) as session:
        with pytest.raises(SQLAlchemyError):
            session.scalar(select(BatchAssessmentItem)).job_id = None
            session.commit()


def test_duplicate_json_and_size_limit(batch_env):
    env = batch_env
    source = imported(env, [{}])
    path = "/api/v1/batch-imports/" + source["import_id"] + "/assessments"
    body = (
        json.dumps(
            {
                "start_assessment": True,
                "policy": "Balanced",
                "import_validation_sha256": source["validation_sha256"],
            }
        )[:-1]
        + ',"start_assessment":true}'
    )
    auth = {
        **env["auth"],
        "Idempotency-Key": "duplicate-batch-json-001",
        "Content-Type": "application/json",
    }
    assert env["client"].post(path, content=body, headers=auth).status_code == 422
    assert env["client"].post(path, content=b"x" * 65537, headers=auth).status_code == 413
    assert total(env, BatchAssessment) == 0


REAL = os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") == "1" and sys.platform == "linux"


@pytest.mark.skipif(not REAL, reason="actual pinned Linux RF/SHAP/PostgreSQL")
@pytest.mark.parametrize("policy", ["Efficiency", "Balanced", "Coverage"])
def test_actual_pipeline_batch_matches_direct_and_reuses_assessments(batch_env, policy):
    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    source = imported(env, [{}, {"income": "0"}])
    first = start(env, source, policy=policy)
    assert first.status_code == 202
    advance(env, first.json()["batch_id"])
    for _ in range(2):
        assert AssessmentWorker(env["ml"], env["ml_token"]).run_once()["status"] == "succeeded"
    status = env["client"].get(first.headers["location"], headers=env["auth"]).json()
    assert status["status"] == "completed" and status["succeeded"] == 2
    results = env["client"].get(first.headers["location"] + "/results", headers=env["auth"]).json()
    direct = AssessmentService(env["engine"])
    for item in results["items"]:
        with Session(env["engine"]) as session:
            case = session.get(Case, UUID(item["case_id"]))
            features = session.get(Alert, case.alert_id).features
        actual = direct._compute(env["actor_id"], UUID(item["case_id"]), features, policy)
        output = item["assessment"]
        assert output["score"] == actual["score"]["score"]
        assert output["recommended_route"] == actual["policy"]["recommended_route"]
        assert output["explanation"]["base_value"] == actual["explanation"]["base_value"]
        assert output["explanation"]["features"] == list(actual["explanation"]["features"])
        assert output["policy_trace"]["override_reason"] == actual["policy"]["override_reason"]
        assert output["human_decision_required"] is True
    assert total(env, Assessment) == 2 and total(env, AssessmentJob) == 2
    # Reimport same sources/cases: new batch skips compatible verified results, no new ML jobs.
    other = imported(env, [{}, {"income": "0"}])
    again = start(env, other, policy=policy)
    outcome = advance(env, again.json()["batch_id"])
    assert outcome.already_assessed == outcome.skipped == 2 and total(env, AssessmentJob) == 2


@pytest.mark.skipif(not REAL, reason="actual pinned Linux in-flight revocation")
@pytest.mark.parametrize("revocation", ["bulk_role", "assignment"])
def test_actual_batch_result_cannot_publish_after_bulk_permission_revocation(
    batch_env, monkeypatch, revocation
):
    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    first = start(env, imported(env, [{}]))
    advance(env, first.json()["batch_id"])
    worker = AssessmentWorker(env["ml"], env["ml_token"])
    actual = worker.runner.run

    def revoke(*args):
        result = actual(*args)
        with Session(env["engine"]) as session, session.begin():
            if revocation == "bulk_role":
                session.get(User, env["actor_id"]).role = "supervisor"
            else:
                case = session.scalar(select(Case))
                case.assigned_to = env["actor_id"]
                case.version += 1
        return result

    monkeypatch.setattr(worker.runner, "run", revoke)
    assert worker.run_once()["status"] == "failed" and total(env, Assessment) == 0
    with Session(env["engine"]) as session:
        job = session.scalar(select(AssessmentJob))
        assert (
            job.failure_code
            == ("authorization_changed" if revocation == "bulk_role" else "stale_case")
            and job.fallback_route == "manual_review"
        )


@pytest.mark.skipif(not REAL, reason="actual Linux worker failure/restart and approved ML")
def test_real_worker_crash_then_restart_produces_one_assessment(batch_env, monkeypatch):
    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    first = start(env, imported(env, [{}]))
    bid = first.json()["batch_id"]
    advance(env, bid)
    broken = AssessmentWorker(env["ml"], env["ml_token"])
    monkeypatch.setattr(
        broken.runner, "_command", lambda: [sys.executable, "-c", "import os; os._exit(17)"]
    )
    assert broken.run_once()["status"] == "pending"
    state = env["batch"].get(env["actor_id"], UUID(bid))
    assert state.queued == state.retrying == 1 and state.failed_manual_review == 0
    with Session(env["engine"]) as session, session.begin():
        job = session.scalar(select(AssessmentJob))
        job.available_at = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)
    restarted = AssessmentWorker(env["ml"], env["ml_token"])
    assert restarted.run_once()["status"] == "succeeded"
    complete = env["batch"].get(env["actor_id"], UUID(bid))
    assert (
        complete.succeeded == 1
        and complete.status == "completed"
        and total(env, Assessment) == 1
        and total(env, AssessmentJob) == 1
    )


def test_expired_ml_lease_recovery_is_reflected_in_batch_counts(batch_env):
    from app.services.assessment_jobs import LeaseLost

    env = batch_env
    first = start(env, imported(env, [{}]))
    advance(env, first.json()["batch_id"])
    old = env["ml"].claim(env["ml_token"])
    with Session(env["engine"]) as session, session.begin():
        session.get(AssessmentJob, old.job_id).lease_until = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(seconds=1)
    assert env["ml"].recover_expired(env["ml_token"]) == 1
    with pytest.raises(LeaseLost):
        env["ml"].prepare(env["ml_token"], old)
    state = env["batch"].get(env["actor_id"], UUID(first.json()["batch_id"]))
    assert state.queued == state.retrying == 1 and state.running == state.failed_manual_review == 0


def test_two_import_batches_adopt_one_pending_case_job(batch_env):
    env = batch_env
    source = imported(env, [{}])
    first = start(env, source)
    second_source = imported(env, [{}])
    second = start(env, second_source)
    assert first.json()["batch_id"] != second.json()["batch_id"]
    batch_ids = [first.json()["batch_id"], second.json()["batch_id"]]
    for bid in batch_ids:
        due(env, bid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda bid: env["batch"].advance(UUID(bid)),
                batch_ids,
            )
        )
    # A due-time/nonblocking dispatcher poll need not immediately adopt a committed job.
    # Require eventual adoption and check uniqueness throughout; never manufacture another job.
    deadline = time.monotonic() + 10
    while not all(r is not None and r.queued == 1 for r in results) and time.monotonic() < deadline:
        assert total(env, AssessmentJob) <= 1
        results = [advance(env, bid) for bid in batch_ids]
        time.sleep(0.02)
    assert all(r is not None and r.queued == 1 for r in results)
    assert total(env, AssessmentJob) == 1
    with Session(env["engine"]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(BatchAssessmentItem)
                .where(BatchAssessmentItem.originated.is_(True))
            )
            == 1
        )


def test_dispatch_database_disconnect_rolls_back_jobs_and_links(batch_env, monkeypatch):
    env = batch_env
    first = start(env, imported(env, [{}, {}]))
    bid = UUID(first.json()["batch_id"])
    original = env["batch"].queue.enqueue_in_transaction

    def disconnect(session, *args, **kwargs):
        result = original(session, *args, **kwargs)
        pid = session.scalar(text("SELECT pg_backend_pid()"))
        with env["engine"].begin() as control:
            assert control.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        return result

    with monkeypatch.context() as patch:
        patch.setattr(env["batch"].queue, "enqueue_in_transaction", disconnect)
        with pytest.raises(AssessmentUnavailable):
            env["batch"].advance(bid)
    assert total(env, AssessmentJob) == 0
    assert env["batch"].advance(bid).queued == 2


def test_version_drift_stops_dispatch_without_scoring(batch_env, monkeypatch):
    import app.services.batch_assessments as module

    env = batch_env
    first = start(env, imported(env, [{}]))
    bid = UUID(first.json()["batch_id"])
    monkeypatch.setattr(module, "MODEL_SHA", "0" * 64)
    value = env["batch"].advance(bid)
    assert (
        value.status == "stopped"
        and value.failed_manual_review == 1
        and value.reason_code == "provenance_changed"
    )
    assert total(env, AssessmentJob) == total(env, Assessment) == 0


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux dispatcher process death")
@pytest.mark.parametrize("after_commit", [False, True])
def test_dispatcher_process_crash_recovers_without_duplicate_jobs(batch_env, after_commit):
    env = batch_env
    first = start(env, imported(env, [{}, {}]))
    bid = first.json()["batch_id"]
    child = r"""
import os,json,sys,secrets
from uuid import UUID
from app.core.config import Settings
from app.core.database import make_engine
from app.services.batch_assessments import BatchAssessmentService
cfg=json.loads(sys.stdin.read())
settings=Settings(_env_file=None,jwt_secret=secrets.token_urlsafe(48),database_url=cfg['url'],batch_assessment_group_size=2)
service=BatchAssessmentService(make_engine(cfg['url']),settings)
if not cfg['after_commit']:
    original=service.queue.enqueue_in_transaction
    def die(*args,**kwargs):
        result=original(*args,**kwargs)
        os._exit(23)
    service.queue.enqueue_in_transaction=die
service.advance(UUID(cfg['batch_id']))
os._exit(23)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", child],
        input=json.dumps(
            {
                "url": env["engine"].url.render_as_string(hide_password=False),
                "batch_id": bid,
                "after_commit": after_commit,
            }
        ),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=25,
    )
    assert result.returncode == 23
    assert total(env, AssessmentJob) == (2 if after_commit else 0)
    assert advance(env, bid).queued == 2 and total(env, AssessmentJob) == 2
