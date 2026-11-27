"""Bounded test-worker protocol; never reflect child text or credentials in failures."""

import json
import os
import select
import time

ERROR_TYPES = {
    "ClockUnavailable",
    "EvidenceNotFound",
    "InvestigationLeaseLost",
    "SnapshotStale",
    "ReadInvalid",
    "EvidenceUnavailable",
    "OperationalError",
    "WorkerFailure",
}

RETRIEVAL_WORKER_SCRIPT = """
import json,sys,signal
p=json.loads(sys.stdin.readline());nonce=p['nonce'];phase='startup'
allowed={'ClockUnavailable','EvidenceNotFound','InvestigationLeaseLost','SnapshotStale',
         'ReadInvalid','EvidenceUnavailable','OperationalError'}
def emit(event,**extra):
    print(json.dumps(dict(event=event,nonce=nonce,phase=phase,**extra)),flush=True)
def safe_exception(kind,value,traceback):
    emit('error',error_type=kind.__name__ if kind.__name__ in allowed else 'WorkerFailure')
sys.excepthook=safe_exception
emit('progress')
from app.core.config import Settings
from app.core.database import make_engine
from app.services.investigation_coordinator import InvestigationCoordinator
settings=Settings(database_url=p['database_url'],jwt_secret=p['jwt_secret'])
engine=make_engine(settings.database_url)
s=InvestigationCoordinator(engine,settings)
phase='claim';emit('progress')
if 'test_claim_utc' in p:
    from datetime import datetime
    sys.path.insert(0,'backend/tests')
    from test_snapshot_clock_integrity import clock_view
    with clock_view(engine,datetime.fromisoformat(p['test_claim_utc'])):
        c=s.claim(p['token'])
else:
    c=s.claim(p['token'])
original=s.reader.get_transactions
def paused(*args):
    global phase
    result=original(*args)
    phase='retrieval';emit('retrieved')
    signal.pause()
s.reader.get_transactions=paused
phase='assembly';emit('progress')
if 'test_clock_utc' in p:
    from datetime import datetime
    sys.path.insert(0,'backend/tests')
    from test_snapshot_clock_integrity import clock_view
    with clock_view(engine,datetime.fromisoformat(p['test_clock_utc'])):
        s.assemble(p['token'],c)
else:
    s.assemble(p['token'],c)
"""


class WorkerHandshakeError(AssertionError):
    pass


def wait_for_retrieval(process, nonce, timeout=20):
    deadline = time.monotonic() + timeout
    pending = b""
    received = 0
    last_phase = "bootstrap"
    while True:
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError):
                raise WorkerHandshakeError("invalid_worker_handshake") from None
            if type(message) is not dict or set(message) not in (
                {"event", "nonce", "phase"},
                {"event", "nonce", "phase", "error_type"},
            ):
                raise WorkerHandshakeError("invalid_worker_handshake")
            if type(message["nonce"]) is not str or message["nonce"] != nonce:
                raise WorkerHandshakeError("worker_handshake_nonce_mismatch")
            if type(message["phase"]) is not str or message["phase"] not in {
                "startup",
                "claim",
                "assembly",
                "retrieval",
            }:
                raise WorkerHandshakeError("invalid_worker_handshake")
            last_phase = message["phase"]
            if message["event"] == "error":
                category = message.get("error_type")
                if type(category) is not str or category not in ERROR_TYPES:
                    category = "WorkerFailure"
                raise WorkerHandshakeError(f"worker_failed:{last_phase}:{category}")
            if (
                message["event"] == "retrieved"
                and last_phase == "retrieval"
                and "error_type" not in message
            ):
                return
            if message["event"] != "progress" or "error_type" in message:
                raise WorkerHandshakeError("invalid_worker_handshake")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerHandshakeError(f"worker_handshake_timeout:{last_phase}")
        readable, _, _ = select.select([process.stdout], [], [], remaining)
        if not readable:
            raise WorkerHandshakeError(f"worker_handshake_timeout:{last_phase}")
        chunk = os.read(process.stdout.fileno(), 4096)
        if not chunk:
            raise WorkerHandshakeError(f"worker_exited_before_retrieval:{last_phase}")
        pending += chunk
        received += len(chunk)
        if received > 16384:
            raise WorkerHandshakeError("worker_handshake_limit")
