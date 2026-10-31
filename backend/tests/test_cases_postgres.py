from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from test_cases import assign, assignment_events

from app.models import Case

pytestmark = pytest.mark.postgres


def test_concurrent_assignment_has_one_winner(platform, case_team):
    client, engine, _, _ = platform
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency check")
    barrier = Barrier(2)

    def reached_update(connection, cursor, statement, parameters, context, many):
        if statement.lower().lstrip().startswith("update cases"):
            barrier.wait(timeout=10)

    event.listen(engine, "before_cursor_execute", reached_update)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(assign, client, case_team, index=0, target=target)
                for target in ["analysttwo", None]
            ]
            responses = [f.result(timeout=20) for f in futures]
    finally:
        event.remove(engine, "before_cursor_execute", reached_update)
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert assignment_events(engine) == 1
    winner = next(r.json() for r in responses if r.status_code == 200)
    with Session(engine) as session:
        case = session.get(Case, UUID(case_team["ids"][0]))
        assert (
            case.version == 2
            and (str(case.assigned_to) if case.assigned_to else None) == winner["assigned_to"]
        )


def test_real_assignment_audit_failure_rolls_back_case(platform, case_team):
    client, engine, _, _ = platform
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger check")
    with engine.begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION reject_assignment_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'private-trigger-marker'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER reject_assignment_audit BEFORE INSERT ON audit_events
        FOR EACH ROW WHEN (NEW.action = 'case.assignment_changed') EXECUTE FUNCTION reject_assignment_audit()""")
        )
    response = assign(client, case_team)
    assert response.status_code == 503 and "private-trigger-marker" not in response.text
    with Session(engine) as session:
        case = session.get(Case, UUID(case_team["ids"][2]))
        assert case.assigned_to is None and case.version == 1
    assert assignment_events(engine) == 0
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER reject_assignment_audit ON audit_events"))
        connection.execute(text("DROP FUNCTION reject_assignment_audit()"))
    assert assign(client, case_team).status_code == 200


def test_concurrent_login_limit_is_shared(platform):
    client, _, settings, _ = platform
    settings.login_attempt_limit = 2
    if platform[1].dialect.name != "postgresql":
        pytest.skip("PostgreSQL throttle check")
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/api/v1/auth/token", json={"username": "unknown", "password": "invalid"}
                ),
                range(4),
            )
        )
    assert sorted(r.status_code for r in responses) == [401, 401, 429, 429]
