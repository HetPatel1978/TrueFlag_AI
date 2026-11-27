"""Linux subprocess failure isolation and actual pinned RF/SHAP/PostgreSQL acceptance."""

import os
import secrets
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_assessment_jobs import jobs as _jobs_fixture
from test_assessments import assessment_setup as _assessment_fixture
from test_assessments import counts

from app.models import Case
from app.services.assessment_jobs import AssessmentJobService, WorkerDenied, WorkerLimits
from app.workers.assessment_worker import AssessmentWorker

assessment_setup = _assessment_fixture
jobs = _jobs_fixture
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def require_linux_postgres(platform):
    if sys.platform != "linux" or platform[1].dialect.name != "postgresql":
        pytest.skip("Actual Linux process isolation and PostgreSQL required")


@pytest.mark.parametrize(
    "program,reason",
    [
        ("import time; time.sleep(60)", "execution_timeout"),
        ("import os; os._exit(9)", "child_failed"),
        ("print('invalid-json')", "invalid_child_output"),
        ("import sys; sys.stdout.write('x'*300000)", "invalid_child_output"),
    ],
)
def test_real_subprocess_failure_isolation(platform, jobs, monkeypatch, program, reason, capsys):
    queue, token, request, _, _ = jobs
    queue.limits = WorkerLimits(3, 1, 1)
    queue.enqueue(**request)
    worker = AssessmentWorker(queue, token)
    # Negative tests run real OS children; no synthetic producer is claimed as actual ML success.
    monkeypatch.setattr(worker.runner, "_command", lambda: [sys.executable, "-c", program])
    result = worker.run_once()
    assert result["status"] == "pending" and result["failure_code"] == reason
    assert counts(platform[1]) == [0] * 5
    captured = capsys.readouterr()
    assert "invalid-json" not in captured.out and "invalid-json" not in captured.err


def test_child_stderr_is_not_customer_logging(platform, jobs, monkeypatch, capsys):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    worker = AssessmentWorker(queue, token)
    monkeypatch.setattr(
        worker.runner,
        "_command",
        lambda: [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('private-feature-marker'); sys.exit(1)",
        ],
    )
    assert worker.run_once()["failure_code"] == "child_failed"
    captured = capsys.readouterr()
    assert "private-feature-marker" not in captured.out + captured.err


def test_heartbeat_keeps_running_child_lease_alive(platform, jobs, monkeypatch):
    queue, token, request, _, _ = jobs
    queue.limits = WorkerLimits(3, 8, 1)
    queue.enqueue(**request)
    worker = AssessmentWorker(queue, token)
    monkeypatch.setattr(
        worker.runner,
        "_command",
        lambda: [sys.executable, "-c", "import time; time.sleep(4); print('{}')"],
    )
    heartbeat = queue.heartbeat
    renewals = []

    def renew(*args):
        heartbeat(*args)
        renewals.append(True)
        assert queue.recover_expired(token) == 0

    monkeypatch.setattr(queue, "heartbeat", renew)
    assert worker.run_once()["failure_code"] == "invalid_child_output"
    assert len(renewals) >= 2


def test_worker_revocation_kills_child(platform, case_team, jobs, monkeypatch):
    queue, token, request, _, identity = jobs
    queue.limits = WorkerLimits(3, 10, 1)
    queue.enqueue(**request)
    worker = AssessmentWorker(queue, token)
    monkeypatch.setattr(
        worker.runner, "_command", lambda: [sys.executable, "-c", "import time; time.sleep(60)"]
    )
    heartbeat = queue.heartbeat

    def revoke(*args):
        queue.revoke_worker(admin_id=UUID(case_team["users"]["admin"]), worker_id=identity)
        return heartbeat(*args)

    monkeypatch.setattr(queue, "heartbeat", revoke)
    with pytest.raises(WorkerDenied):
        worker.run_once()
    assert counts(platform[1]) == [0] * 5


def test_shutdown_cancels_child_safely(platform, jobs, monkeypatch):
    queue, token, request, _, _ = jobs
    queue.enqueue(**request)
    stop = threading.Event()
    stop.set()
    worker = AssessmentWorker(queue, token, stop)
    monkeypatch.setattr(
        worker.runner, "_command", lambda: [sys.executable, "-c", "import time; time.sleep(60)"]
    )
    assert worker.run_once()["status"] == "pending"
    assert counts(platform[1]) == [0] * 5


def test_watchdog_kills_child_during_blocked_heartbeat(jobs, monkeypatch):
    import subprocess

    queue, token, request, _, _ = jobs
    queue.limits = WorkerLimits(3, 2, 1)
    queue.enqueue(**request)
    worker = AssessmentWorker(queue, token)
    monkeypatch.setattr(
        worker.runner, "_command", lambda: [sys.executable, "-c", "import time; time.sleep(60)"]
    )
    original = subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    heartbeat = queue.heartbeat

    def blocked(*args):
        heartbeat(*args)
        threading.Event().wait(3)
        assert children[0].poll() is not None  # Watchdog does not wait for blocked DB I/O.

    monkeypatch.setattr(queue, "heartbeat", blocked)
    assert worker.run_once()["failure_code"] == "execution_timeout"


def test_actual_child_dies_when_supervisor_is_killed():
    import ctypes
    import signal
    import subprocess
    import time

    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert (
        libc.prctl(36, 1, 0, 0, 0) == 0
    )  # Reap the orphan in the test, rather than leak a zombie.
    program = """import os,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-B','-m','app.workers.assessment_child',str(os.getpid())],
    stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(child.pid,flush=True)
time.sleep(60)
"""
    parent = subprocess.Popen([sys.executable, "-c", program], stdout=subprocess.PIPE)
    child_pid = None
    reaped = False
    try:
        child_pid = int(parent.stdout.readline())
        threading.Event().wait(1)
        parent.kill()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pid, status = os.waitpid(child_pid, os.WNOHANG)
            if pid:
                reaped = True
                assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
                break
            threading.Event().wait(0.05)
        assert reaped
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        parent.stdout.close()
        if child_pid and not reaped:
            try:
                os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="Explicit actual pinned RF/SHAP acceptance required",
)
@pytest.mark.parametrize("income", [None, 0])
def test_actual_worker_scores_unseen_synthetic_record(platform, case_team, alert_payload, income):
    queue = AssessmentJobService(platform[1], limits=WorkerLimits(15, 60, 2))
    token = secrets.token_hex(32)
    queue.register_worker(
        admin_id=UUID(case_team["users"]["admin"]), name="real-linux-worker", token=token
    )
    alert_payload["source_id"] = "synthetic-unseen-worker-" + uuid4().hex
    alert_payload["features"].update(state="QZ", income=income)
    field = next(
        f for f in alert_payload["features"] if f not in {"state", "income", "kycRiskScore"}
    )
    alert_payload["features"][field] = 37
    response = platform[0].post(
        "/api/v1/alerts",
        json=alert_payload,
        headers={**case_team["auth"]["admin"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    case_id = UUID(response.json()["case_id"])
    request = dict(
        actor_id=UUID(case_team["users"]["admin"]),
        case_id=case_id,
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="real-background-job",
        policy="Coverage",
    )
    queued, _ = queue.enqueue(**request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(AssessmentWorker(queue, token).run_once) for _ in range(2)]
        outcomes = [f.result(timeout=80) for f in futures]
    assert sum(result is None for result in outcomes) == 1
    result = next(r for r in outcomes if r)
    assert result["status"] == "succeeded" and result["attempts"] == 1
    assert result["job_id"] == queued["job_id"] and counts(platform[1]) == [1] * 5
    assessment = queue.assessments.get(
        actor_id=request["actor_id"], case_id=case_id, assessment_id=UUID(result["assessment_id"])
    )
    assert assessment["explanation"]["status"] == "verified"
    assert next(
        f["missing"] for f in assessment["explanation"]["features"] if f["name"] == "income"
    ) is (income is None)
    assert queue.enqueue(**request) == (result, False)
    assert AssessmentWorker(queue, token).run_once() is None
    with Session(platform[1]) as session:
        case = session.get(Case, case_id)
        assert case.status == "open" and case.version == 1 and case.disposition is None
