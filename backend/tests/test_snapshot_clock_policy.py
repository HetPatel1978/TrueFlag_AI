"""Durable safety state: real PostgreSQL, independent commits and process boundaries."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_snapshot_clock_integrity import anchor, clock_view, read, snapshot

from alembic import command
from app.models.snapshot_clock import SnapshotClock
from app.services.evidence_read import ReadInvalid
from app.services.snapshot_clock import ClockUnavailable, SnapshotTime

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture


def state(engine):
    with Session(engine) as session:
        row = session.get(SnapshotClock, 1)
        return row.high_water, row.epoch, row.regressed, row.used


def test_expired_read_rollback_cannot_erase_floor_or_allow_replay(env):
    engine = env["platform"][1]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        _, request = snapshot(env)
        clock[0] = initial + timedelta(seconds=900)
        with pytest.raises(ReadInvalid):
            read(env, request)
        floor, epoch, _, _ = state(engine)
        assert floor == int(clock[0].timestamp())
        clock[0] -= timedelta(seconds=1)
        with pytest.raises(ClockUnavailable):
            read(env, request)
        assert state(engine) == (floor, epoch + 1, True, True)
        clock[0] = initial + timedelta(seconds=901)
        with pytest.raises(ReadInvalid):
            read(env, request)
        assert state(engine) == (int(clock[0].timestamp()), epoch + 1, False, True)


def test_regression_invalidates_even_not_yet_expired_preincident_tokens(env):
    engine = env["platform"][1]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        original, request = snapshot(env)
        clock[0] -= timedelta(seconds=1)
        with pytest.raises(ClockUnavailable):
            read(env, request)
        clock[0] = initial
        with pytest.raises(ReadInvalid):
            read(env, request)
        fresh, current = snapshot(env)
        assert fresh.snapshot == original.snapshot  # Facts/source identity did not change.
        assert read(env, current).snapshot == original.snapshot


def test_concurrent_regression_observers_increment_epoch_once(env):
    engine = env["platform"][1]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        snapshot(env)
        before = state(engine)
        clock[0] -= timedelta(seconds=1)

        def observe(_):
            with pytest.raises(ClockUnavailable):
                SnapshotTime(engine).observe()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(observe, range(6)))
        assert state(engine) == (before[0], before[1] + 1, True, True)


def test_guard_lock_timeout_fails_closed_and_does_not_release_evidence(env):
    engine = env["platform"][1]
    with Session(engine) as blocker, blocker.begin():
        blocker.scalar(select(SnapshotClock).where(SnapshotClock.id == 1).with_for_update())
        with pytest.raises(ClockUnavailable, match="^snapshot_clock_unavailable$"):
            snapshot(env)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE snapshot_clock SET high_water=high_water-1",
        "UPDATE snapshot_clock SET epoch=epoch+1",
        "UPDATE snapshot_clock SET used=false",
        "DELETE FROM snapshot_clock",
        "TRUNCATE snapshot_clock",
    ],
)
def test_clock_floor_epoch_and_used_history_cannot_be_reset(env, sql):
    engine = env["platform"][1]
    snapshot(env)
    before = state(engine)
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(text(sql))
    assert state(engine) == before


def test_missing_guard_storage_fails_closed(env):
    engine = env["platform"][1]
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE snapshot_clock RENAME TO withheld_clock"))
    try:
        with pytest.raises(ClockUnavailable):
            snapshot(env)
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE withheld_clock RENAME TO snapshot_clock"))


def test_used_guard_downgrade_refuses_to_discard_epoch_history(env):
    from pathlib import Path

    snapshot(env)
    with pytest.raises(RuntimeError, match="retained snapshot clock history"):
        command.downgrade(
            Config(str(Path(__file__).parents[1] / "alembic.ini")), "0015_investigation_drafts"
        )


CHILD = """
import json,os,sys
from datetime import datetime
sys.path.insert(0,'backend/tests')
from app.core.database import make_engine
from app.services.snapshot_clock import SnapshotTime,ClockUnavailable
from test_snapshot_clock_integrity import clock_view
engine=make_engine(os.environ['DATABASE_URL'])
with clock_view(engine,datetime.fromisoformat(os.environ['G032_TEST_INSTANT'])):
 try:
  value=SnapshotTime(engine).observe()
  result={'available':True,'epoch':value.epoch,'second':value.second}
 except ClockUnavailable:
  result={'available':False}
print(json.dumps(result))
engine.dispose()
"""


def child(instant):
    process = subprocess.run(
        [sys.executable, "-B", "-c", CHILD],
        env={**os.environ, "G032_TEST_INSTANT": instant.isoformat()},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 0
    return json.loads(process.stdout)


def test_api_worker_and_fresh_processes_share_regression_state(env):
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("Pinned supported subprocess runtime required")
    engine = env["platform"][1]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        _, request = snapshot(env)
        clock[0] += timedelta(seconds=900)
        with pytest.raises(ReadInvalid):
            read(env, request)
        before = state(engine)
        assert child(initial + timedelta(seconds=899)) == {"available": False}
        assert state(engine) == (before[0], before[1] + 1, True, True)
        # A fresh interpreter cannot forget the preceding process's detection.
        assert child(initial + timedelta(seconds=899)) == {"available": False}
        resumed = child(initial + timedelta(seconds=901))
        assert resumed["available"] and resumed["epoch"] == before[1] + 1
        clock[0] = initial + timedelta(seconds=901)
        with pytest.raises(ReadInvalid):
            read(env, request)
