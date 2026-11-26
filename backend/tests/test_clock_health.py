"""Clock-aware readiness preserves liveness and never authorizes stale tokens."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_snapshot_clock_integrity import anchor, clock_view, read, snapshot

from app.models.snapshot_clock import SnapshotClock
from app.services.evidence_read import ReadInvalid

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture


def test_readiness_rejects_regression_and_recovers_without_reviving_tokens(env):
    client, engine = env["platform"][:2]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        _, old = snapshot(env)
        assert client.get("/ready").json() == {"status": "ready"}
        clock[0] -= timedelta(seconds=1)
        response = client.get("/ready")
        assert response.status_code == 503 and response.json() == {"status": "not_ready"}
        assert response.headers["X-Readiness-Code"] == "snapshot_clock_unavailable"
        assert client.get("/health").json()["status"] == "ok"
        with Session(engine) as session:
            assert session.get(SnapshotClock, 1).epoch == 2
        clock[0] = initial
        assert client.get("/ready").status_code == 200
        with pytest.raises(ReadInvalid):
            read(env, old)
        _, fresh = snapshot(env)
        assert read(env, fresh).data.total == 12


def test_readiness_missing_time_state_is_sanitized(env):
    client, engine = env["platform"][:2]
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE snapshot_clock RENAME TO withheld_clock"))
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.headers["X-Readiness-Code"] == "snapshot_clock_unavailable"
        assert response.json() == {"status": "not_ready"}
        assert "SELECT" not in response.text and "snapshot_clock" not in response.text
        assert client.get("/health").status_code == 200
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE withheld_clock RENAME TO snapshot_clock"))


def test_incompatible_release_does_not_observe_or_reset_time(env):
    client, engine = env["platform"][:2]
    with Session(engine) as session:
        row = session.get(SnapshotClock, 1)
        before = (row.high_water, row.epoch, row.used)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num='0015_investigation_drafts'")
        )
    response = client.get("/ready")
    assert (
        response.status_code == 503
        and response.headers["X-Readiness-Code"] == "schema_incompatible"
    )
    with Session(engine) as session:
        row = session.get(SnapshotClock, 1)
        assert (row.high_water, row.epoch, row.used) == before
