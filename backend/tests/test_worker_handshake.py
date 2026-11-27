"""Actual Linux pipes exercise framing, correlation, safe failure and one deadline."""

import json
import subprocess
import sys

import pytest
from worker_handshake import WorkerHandshakeError, wait_for_retrieval

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux worker pipe/select contract")


def execute(script, *, nonce="test-nonce", timeout=20):
    process = subprocess.Popen([sys.executable, "-B", "-c", script], stdout=subprocess.PIPE)
    try:
        wait_for_retrieval(process, nonce, timeout)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


def test_multiple_protocol_frames_in_one_pipe_write():
    frames = [
        {"event": "progress", "nonce": "test-nonce", "phase": "startup"},
        {"event": "progress", "nonce": "test-nonce", "phase": "assembly"},
        {"event": "retrieved", "nonce": "test-nonce", "phase": "retrieval"},
    ]
    data = "\n".join(json.dumps(frame) for frame in frames) + "\n"
    execute("import sys;sys.stdout.write(" + repr(data) + ");sys.stdout.flush()")


@pytest.mark.parametrize("category", ["ClockUnavailable", "EvidenceNotFound", "OperationalError"])
def test_safe_child_failure_classification(category):
    data = json.dumps(
        {"event": "error", "nonce": "test-nonce", "phase": "assembly", "error_type": category}
    )
    with pytest.raises(WorkerHandshakeError, match="^worker_failed:assembly:" + category + "$"):
        execute("print(" + repr(data) + ",flush=True)")


def test_wrong_nonce_is_not_readiness():
    data = json.dumps({"event": "retrieved", "nonce": "wrong", "phase": "retrieval"})
    with pytest.raises(WorkerHandshakeError, match="^worker_handshake_nonce_mismatch$"):
        execute("print(" + repr(data) + ",flush=True)")


def test_eof_is_not_readiness():
    with pytest.raises(WorkerHandshakeError, match="^worker_exited_before_retrieval:bootstrap$"):
        execute("pass")


def test_raw_child_text_is_never_reflected():
    with pytest.raises(WorkerHandshakeError, match="^invalid_worker_handshake$") as error:
        execute("print('synthetic-secret-marker',flush=True)")
    assert "synthetic-secret-marker" not in str(error.value)


def test_timeout_remains_bounded_without_response():
    with pytest.raises(WorkerHandshakeError, match="^worker_handshake_timeout:bootstrap$"):
        execute("import time;time.sleep(5)", timeout=0.15)


def test_oversized_output_is_rejected():
    with pytest.raises(WorkerHandshakeError, match="^worker_handshake_limit$"):
        execute("import sys;sys.stdout.write('x'*20000);sys.stdout.flush()")
