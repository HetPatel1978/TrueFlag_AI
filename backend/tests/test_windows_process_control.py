"""Actual Windows Job Objects/pipes; no database or paid transport."""

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.workers.process_control import (
    ProcessCancelled,
    ProcessOutputLimit,
    ProcessTimeout,
    WindowsJob,
    kernel,
    run_windows,
    start_in_job,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows kernel containment")
ENV = {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}


def execute(code, payload=b"", **options):
    return run_windows(
        [sys.executable, "-B", "-c", code],
        payload,
        environment=ENV,
        timeout=options.pop("timeout", 5),
        max_output=options.pop("max_output", 4096),
        memory_bytes=384 * 1024 * 1024,
        cpu_seconds=12,
        **options,
    )


def test_exact_job_membership_limits_and_pipe_roundtrip():
    code, raw = execute(
        "import sys; from app.workers.process_control import require_windows_child_limits; require_windows_child_limits(384*1024*1024); sys.stdout.buffer.write(sys.stdin.buffer.read())",
        b"synthetic-only",
    )
    assert code == 0 and raw == b"synthetic-only"


def test_output_overflow_is_rejected_and_child_terminated():
    with pytest.raises(ProcessOutputLimit):
        execute(
            "import sys; sys.stdout.buffer.write(b'x'*32768);sys.stdout.flush()", max_output=1024
        )


def test_timeout_is_bounded_without_windows_select_on_pipe():
    before = time.monotonic()
    with pytest.raises(ProcessTimeout):
        execute("import time; time.sleep(30)", timeout=0.4)
    assert time.monotonic() - before < 8


def test_cancelled_request_never_launches_or_sends_input(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("cancelled child launched")
    )
    with pytest.raises(ProcessCancelled):
        execute("print('must not run')", cancelled=stop)


def test_only_allowlisted_environment_reaches_child(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic_sentinel_not_real")
    code, raw = execute("import os;print('ANTHROPIC_API_KEY' in os.environ)")
    assert code == 0 and raw.strip() == b"False"


def test_uncontained_direct_child_is_rejected():
    p = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.workers.process_control import require_windows_child_limits; require_windows_child_limits(384*1024*1024)",
        ],
        env={**os.environ, **ENV, "TRUEFLAG_CHILD_JOB": ""},
        capture_output=True,
        timeout=8,
    )
    assert p.returncode != 0


def test_job_close_kills_running_child_tree():
    job = WindowsJob(memory_bytes=384 * 1024 * 1024, cpu_seconds=12)
    p = start_in_job(
        job,
        [sys.executable, "-c", "import os,time;print(os.getpid(),flush=True);time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    child_handle = None
    try:
        messages = queue.Queue()
        threading.Thread(target=lambda: messages.put(p.stdout.readline()), daemon=True).start()
        actual_pid = int(messages.get(timeout=5))
        api = kernel()
        from ctypes import wintypes

        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        child_handle = api.OpenProcess(0x100000, False, actual_pid)
        assert child_handle
        job.close()
        assert api.WaitForSingleObject(child_handle, 5000) == 0
        p.wait(timeout=5)  # Windows job-close termination can report code zero.
    finally:
        if child_handle:
            api.CloseHandle(child_handle)
        job.close()
        if p.poll() is None:
            p.kill()
        p.wait(timeout=5)
        p.stdout.close()


def test_heartbeat_callback_runs_during_child_execution():
    observations = []
    code, raw = execute(
        "import time;time.sleep(.4);print('done')",
        tick=lambda: observations.append(time.monotonic()),
    )
    assert code == 0 and raw.strip() == b"done" and len(observations) >= 2


def test_nonzero_child_exit_is_returned_without_fabricated_success():
    code, raw = execute("raise SystemExit(7)")
    assert code == 7 and raw == b""
