"""Actual authenticated worker failures must not be mistaken for readiness."""

import json
import secrets
import subprocess
import sys
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import submit
from test_snapshot_clock_integrity import anchor, clock_view
from worker_handshake import RETRIEVAL_WORKER_SCRIPT, WorkerHandshakeError, wait_for_retrieval

from app.models.investigations import InvestigationPacket
from app.models.snapshot_clock import SnapshotClock

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(sys.platform != "linux", reason="Linux worker"),
]
env = investigation_fixture
evidence_setup = evidence_fixture


@pytest.mark.parametrize("fault", ["clock", "authorization"])
def test_authenticated_child_reports_precise_failure_without_false_readiness(env, fault):
    engine = env["platform"][1]
    instant = anchor(env)
    with clock_view(engine, instant):
        submit(env)
    payload = {
        "database_url": env["platform"][2].database_url,
        "jwt_secret": env["platform"][2].jwt_secret.get_secret_value(),
        "token": env["token"] if fault == "clock" else secrets.token_urlsafe(48),
        "nonce": secrets.token_hex(16),
    }
    if fault == "clock":
        payload["test_claim_utc"] = instant.isoformat()
        payload["test_clock_utc"] = (instant - timedelta(seconds=2)).isoformat()
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", RETRIEVAL_WORKER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.close()
    category = "assembly:ClockUnavailable" if fault == "clock" else "claim:EvidenceNotFound"
    try:
        with pytest.raises(WorkerHandshakeError, match="^worker_failed:" + category + "$") as error:
            wait_for_retrieval(process, payload["nonce"], timeout=20)
        assert payload["token"] not in str(error.value)
        assert payload["jwt_secret"] not in str(error.value)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0
        if fault == "clock":
            state = session.get(SnapshotClock, 1)
            assert state.regressed and state.epoch == 2
