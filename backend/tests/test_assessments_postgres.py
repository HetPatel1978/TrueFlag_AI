"""Real PostgreSQL races, database failures and lock/immutability acceptance."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_assessments import assessment_setup as _assessment_fixture
from test_assessments import counts

from app.models import User
from app.services.assessments import AssessmentConflict, AssessmentUnavailable

pytestmark = pytest.mark.postgres
assessment_setup = _assessment_fixture


@pytest.fixture(autouse=True)
def require_postgres(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL locks, triggers and concurrency")


@pytest.mark.parametrize("same_run", [True, False])
def test_concurrent_requests(platform, assessment_setup, monkeypatch, same_run):
    service, request, _ = assessment_setup
    compute = service._compute
    barrier = Barrier(2)

    def synchronized(*args):
        result = compute(*args)
        barrier.wait(timeout=20)
        return result

    monkeypatch.setattr(service, "_compute", synchronized)
    second = (
        request
        if same_run
        else {**request, "run_id": uuid4(), "idempotency_key": "parallel-new-run"}
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.assess, **r) for r in [request, second]]
        results = [f.result(timeout=30) for f in futures]
    if same_run:
        assert sorted(created for _, created in results) == [False, True]
        assert {r["assessment_id"] for r, _ in results}.__len__() == 1
        assert counts(platform[1]) == [1] * 5
    else:
        assert all(created for _, created in results)
        assert sorted(r["version"] for r, _ in results) == [1, 2]
        assert counts(platform[1]) == [2] * 5


@pytest.mark.parametrize("conflict", ["policy", "cross_case_key", "cross_case_run"])
def test_concurrent_conflicting_submissions(
    platform, case_team, assessment_setup, monkeypatch, conflict
):
    service, request, _ = assessment_setup
    request = {**request, "actor_id": UUID(case_team["users"]["admin"])}
    compute = service._compute
    barrier = Barrier(2)

    def synchronized(*args):
        result = compute(*args)
        barrier.wait(timeout=20)
        return result

    monkeypatch.setattr(service, "_compute", synchronized)
    second = {**request, "policy": "Balanced"}
    if conflict != "policy":
        second = {**request, "case_id": UUID(case_team["ids"][1])}
        second["run_id" if conflict == "cross_case_key" else "idempotency_key"] = (
            uuid4() if conflict == "cross_case_key" else "different-cross-case-key"
        )

    def submit(r):
        try:
            return service.assess(**r)[1]
        except AssessmentConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, r) for r in [request, second]]
        outcomes = [f.result(timeout=30) for f in futures]
    assert outcomes.count(True) == 1 and outcomes.count("conflict") == 1
    assert counts(platform[1]) == [1] * 5


def test_database_audit_trigger_failure_rolls_back(platform, assessment_setup):
    service, request, _ = assessment_setup
    with platform[1].begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION reject_assessment_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-database-marker'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER reject_assessment_audit BEFORE INSERT ON audit_events
            FOR EACH ROW WHEN (NEW.action = 'assessment.completed')
            EXECUTE FUNCTION reject_assessment_audit()""")
        )
    with pytest.raises(AssessmentUnavailable) as error:
        service.assess(**request)
    assert str(error.value) == "assessment_database_unavailable"
    assert counts(platform[1]) == [0] * 5
    with platform[1].begin() as connection:
        connection.execute(text("DROP TRIGGER reject_assessment_audit ON audit_events"))
        connection.execute(text("DROP FUNCTION reject_assessment_audit()"))
    assert service.assess(**request)[1]


def test_revocation_serializes_with_commit(platform, assessment_setup):
    service, request, _ = assessment_setup
    inserting, release, revoking = Event(), Event(), Event()

    def hold_write(connection, cursor, statement, parameters, context, many):
        if statement.lower().startswith("insert into assessments"):
            inserting.set()
            assert release.wait(timeout=20)

    def revoke():
        revoking.set()
        with Session(platform[1]) as session, session.begin():
            user = session.scalar(
                select(User).where(User.id == request["actor_id"]).with_for_update()
            )
            user.active = False

    event.listen(platform[1], "before_cursor_execute", hold_write)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            creating = pool.submit(service.assess, **request)
            assert inserting.wait(timeout=20)
            revocation = pool.submit(revoke)
            assert revoking.wait(timeout=10)
            assert not revocation.done()
            release.set()
            assert creating.result(timeout=20)[1]
            revocation.result(timeout=20)
    finally:
        release.set()
        event.remove(platform[1], "before_cursor_execute", hold_write)
    assert counts(platform[1]) == [1] * 5
    from app.services.assessments import AssessmentNotFound

    with pytest.raises(AssessmentNotFound):
        service.list(actor_id=request["actor_id"], case_id=request["case_id"])


@pytest.mark.parametrize(
    "table", ["assessments", "assessment_explanations", "model_scores", "decisions", "audit_events"]
)
def test_truncate_cannot_remove_history(platform, assessment_setup, table):
    service, request, _ = assessment_setup
    service.assess(**request)
    with pytest.raises(DBAPIError, match="immutable_assessment_record"):
        with platform[1].begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    assert counts(platform[1]) == [1] * 5


def test_read_detects_tampering_even_if_owner_disables_trigger(platform, assessment_setup):
    service, request, _ = assessment_setup
    result, _ = service.assess(**request)
    # Test owner demonstrates digest detection, not immunity against a privileged DBA.
    with platform[1].begin() as connection:
        connection.execute(text("ALTER TABLE model_scores DISABLE TRIGGER protect_model_scores"))
        connection.execute(text("UPDATE model_scores SET score = 0.99"))
        connection.execute(text("ALTER TABLE model_scores ENABLE TRIGGER protect_model_scores"))
    with pytest.raises(AssessmentUnavailable, match="assessment_integrity_failed"):
        service.get(
            actor_id=request["actor_id"],
            case_id=request["case_id"],
            assessment_id=UUID(result["assessment_id"]),
        )
