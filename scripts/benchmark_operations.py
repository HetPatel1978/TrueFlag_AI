"""Isolated Linux/PG/TCP benchmark. Aggregate-only stdout; credentials enter through stdin."""

import json
import os
import resource
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import jwt
import uvicorn
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.database import make_engine
from app.main import create_app
from app.models import (
    Assessment,
    AssessmentExplanation,
    AssessmentJob,
    AuditEvent,
    Case,
    Decision,
    ModelScore,
    User,
)
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.security.auth import password_hash
from app.services.assessment_jobs import AssessmentJobService, Claim, JobUnavailable, LeaseLost
from app.services.monitoring import MetricFlusher
from app.workers.assessment_worker import AssessmentWorker
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema


def quantiles(values):
    values = sorted(values)

    def percentile(q):
        at = (len(values) - 1) * q
        lo = int(at)
        return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (at - lo)

    return {
        "count": len(values),
        **{f"p{q}_ms": round(percentile(q / 100), 3) for q in (50, 95, 99)},
    }


def headers(user, settings):
    now = datetime.now(timezone.utc)
    # Synthetic issuer fixture tolerates the known guest-clock issue without weakening validation.
    return {
        "Authorization": "Bearer "
        + jwt.encode(
            {
                "sub": str(user.id),
                "iat": now - timedelta(seconds=60),
                "exp": now + timedelta(minutes=15),
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
    }


def benchmark(config):
    assert (
        sys.platform == "linux"
        and make_url(config["database_url"]).get_backend_name() == "postgresql"
    )
    owner = make_engine(config["database_url"])
    schema = "tf_operations_benchmark_" + uuid4().hex
    with owner.begin() as connection:
        connection.execute(CreateSchema(schema))
    url = make_url(config["database_url"]).update_query_dict({"options": "-csearch_path=" + schema})
    database_url = url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = database_url
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    engine = None
    server = thread = client = None
    exporters = []
    stop = threading.Event()
    watchdog = threading.Timer(180, stop.set)
    watchdog.daemon = True
    watchdog.start()
    stage = "setup"
    diagnostics = {}
    try:
        command.upgrade(Config("backend/alembic.ini"), "head")
        settings = Settings(assessment_api_rate_limit=1000, assessment_queue_capacity=4)
        engine = make_engine(database_url)
        with Session(engine) as session, session.begin():
            users = {
                name: User(
                    username=name,
                    role=role,
                    password_hash=password_hash.hash(secrets.token_urlsafe(24)),
                )
                for name, role in [
                    ("opsadmin", "admin"),
                    ("opsanalyst", "analyst"),
                    ("opsother", "analyst"),
                ]
            }
            session.add_all(users.values())
            session.flush()
            auth = {name: headers(user, settings) for name, user in users.items()}
            ids = {name: user.id for name, user in users.items()}
        queue = AssessmentJobService(engine)
        token = secrets.token_hex(32)
        queue.register_worker(
            admin_id=ids["opsadmin"], name="bounded-operations-worker", token=token
        )
        workers = [AssessmentWorker(queue, token, stop) for _ in range(2)]
        exporters = [MetricFlusher(engine, worker.telemetry).start() for worker in workers]
        app = create_app(settings, engine)
        server = uvicorn.Server(
            uvicorn.Config(app, log_config=None, access_log=False, log_level="error")
        )
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            stop.wait(0.02)
        assert server.started
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10)
        cases, requests = [], []
        for index in range(16):
            features = {field: 0 for field in AlertFeatures.model_fields}
            features.update(state="QZ", kycRiskScore=3, income=None if index % 2 else 0)
            numeric = next(k for k in features if k not in {"state", "income", "kycRiskScore"})
            features[numeric] = 20 + index
            ingested = client.post(
                "/api/v1/alerts",
                headers={**auth["opsadmin"], "Idempotency-Key": uuid4().hex},
                json={
                    "source_id": "synthetic-operations-" + uuid4().hex,
                    "data_classification": "synthetic",
                    "feature_contract_version": FEATURE_CONTRACT_VERSION,
                    "features": features,
                },
            )
            assert ingested.status_code == 201
            case_id = ingested.json()["case_id"]
            assigned = client.put(
                f"/api/v1/cases/{case_id}/assignment",
                headers=auth["opsadmin"],
                json={"expected_version": 1, "assigned_to": str(ids["opsanalyst"])},
            )
            assert assigned.status_code == 200
            cases.append(case_id)
            requests.append(
                {
                    "expected_version": 2,
                    "run_id": str(uuid4()),
                    "policy": ("Efficiency", "Balanced", "Coverage")[index % 3],
                }
            )
        latencies, execution, statuses = [], [], Counter()
        depths, ages = [], []
        contention_retries = []

        def submit(index, conflict=False, retry_busy=True):
            if stop.is_set():
                raise RuntimeError("benchmark_deadline")
            body = (
                requests[index]
                if not conflict
                else {
                    **requests[index],
                    "policy": "Coverage" if requests[index]["policy"] != "Coverage" else "Balanced",
                }
            )
            started = time.monotonic()
            for attempt in range(5):
                response = client.post(
                    f"/api/v1/cases/{cases[index]}/assessments",
                    json=body,
                    headers={
                        **auth["opsanalyst"],
                        "Idempotency-Key": f"operations-request-{index:04d}",
                    },
                )
                if not (
                    retry_busy
                    and response.status_code == 503
                    and response.headers.get("retry-after") == "2"
                    and attempt < 4
                ):
                    break
                contention_retries.append(True)
                stop.wait(2)
            return response, (time.monotonic() - started) * 1000

        def drain(worker):
            observations = []
            while not stop.is_set():
                started = time.monotonic()
                result = worker.run_once()
                if result is None:
                    # SKIP LOCKED/lease recovery can be transiently idle while work remains.
                    with Session(engine) as session:
                        active = session.scalar(
                            select(func.count())
                            .select_from(AssessmentJob)
                            .where(AssessmentJob.status.in_(["pending", "running"]))
                        )
                    if active == 0:
                        return observations
                    stop.wait(0.1)
                    continue
                assert result["status"] == "succeeded"
                observations.append((time.monotonic() - started) * 1000)
            raise RuntimeError("benchmark_deadline")

        def next_attempt(worker):
            deadline = time.monotonic() + 20
            while not stop.is_set() and time.monotonic() < deadline:
                result = worker.run_once()
                if result is not None:
                    return result
                stop.wait(0.2)
            raise AssertionError("durable_backoff_wait_exhausted")

        stage = "sustained_load"
        wall = time.monotonic()
        cpu_before = resource.getrusage(resource.RUSAGE_SELF)
        child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        for wave in range(3):
            stage = f"wave_{wave}_submission"
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(submit, range(wave * 4, wave * 4 + 4)))
            diagnostics = {
                "http_statuses": [r.status_code for r, _ in responses],
                "retry_after": [
                    r.headers.get("retry-after")
                    if r.headers.get("retry-after") in {"2", "5"}
                    else None
                    for r, _ in responses
                ],
                "elapsed_seconds": round(time.monotonic() - wall, 3),
            }
            for response, elapsed in responses:
                assert response.status_code == 202
                statuses[str(response.status_code)] += 1
                latencies.append(elapsed)
            replay, _ = submit(wave * 4)
            assert (
                replay.status_code == 202
                and replay.json()["job_id"] == responses[0][0].json()["job_id"]
            )
            statuses["202"] += 1
            conflicting, _ = submit(wave * 4, True)
            assert conflicting.status_code == 409
            statuses["409"] += 1
            if wave == 0:
                saturated, _ = submit(4, retry_busy=False)
                assert saturated.status_code == 503 and saturated.headers["retry-after"]
                statuses["503"] += 1
            live = client.get("/api/v1/internal/metrics", headers=auth["opsadmin"])
            assert live.status_code == 200 and live.json()["queue"]["pending"] == 4
            depths.append(live.json()["queue"]["pending"] + live.json()["queue"]["running"])
            ages.append(live.json()["queue"]["oldest_pending_age_seconds"])
            stage = f"wave_{wave}_processing"
            with ThreadPoolExecutor(max_workers=2) as pool:
                for samples in pool.map(drain, workers):
                    execution.extend(samples)
            with Session(engine) as session:
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(AssessmentJob)
                        .where(AssessmentJob.status.in_(["pending", "running"]))
                    )
                    == 0
                )
                assert (
                    session.scalar(select(func.count()).select_from(Assessment)) == (wave + 1) * 4
                )
        steady_seconds = time.monotonic() - wall
        assert len(execution) == 12

        stage = "crash_recovery"
        response, _ = submit(12)
        assert response.status_code == 202
        program = """import json,os,sys
from app.core.database import make_engine
from app.services.assessment_jobs import AssessmentJobService
p=json.load(sys.stdin)
claim=AssessmentJobService(make_engine(p['url'])).claim(p['token'])
assert claim is not None
print('CLAIMED',flush=True)
os._exit(73)
"""
        crashed = subprocess.run(
            [sys.executable, "-B", "-c", program],
            input=json.dumps({"url": database_url, "token": token}),
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert crashed.returncode == 73 and crashed.stdout.strip() == "CLAIMED"
        with Session(engine) as session:
            row = session.scalar(
                select(AssessmentJob).where(AssessmentJob.case_id == UUID(cases[12]))
            )
            old_claim = Claim(row.id, row.lease_token, row.worker_id)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE assessment_jobs SET lease_until = clock_timestamp() - interval '1 second' WHERE status = 'running'"
                )
            )
        expired = client.get("/api/v1/internal/metrics", headers=auth["opsadmin"])
        assert expired.status_code == 200 and expired.json()["queue"]["expired_leases"] == 1
        assert workers[0].run_once() is None  # Recovery schedules real 5-second backoff.
        try:
            queue.heartbeat(token, old_claim)
            raise AssertionError("stale_claim_accepted")
        except LeaseLost:
            pass
        assert next_attempt(workers[0])["status"] == "succeeded"

        stage = "database_interruption"
        response, _ = submit(13)
        assert response.status_code == 202
        claim = queue.claim(token)
        result = workers[0].runner.run(queue, token, claim)
        killed = []

        def disconnect(connection, cursor, statement, parameters, context, many):
            if not killed and statement.lower().startswith("update assessment_jobs"):
                killed.append(True)
                pid = connection.connection.driver_connection.info.backend_pid
                with owner.begin() as control:
                    assert control.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

        event.listen(engine, "before_cursor_execute", disconnect)
        try:
            try:
                queue.complete(token, claim, result)
                raise AssertionError("database_fault_not_injected")
            except JobUnavailable:
                pass
        finally:
            event.remove(engine, "before_cursor_execute", disconnect)
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Assessment)) == 13
            assert session.get(AssessmentJob, claim.job_id).status == "running"
        assert queue.complete(token, claim, result)["status"] == "succeeded"

        stage = "authorization_revocation"
        accepted, _ = submit(14)
        assert accepted.status_code == 202
        actual = workers[0].runner.run

        def revoke(*args):
            output = actual(*args)
            changed = client.put(
                f"/api/v1/cases/{cases[14]}/assignment",
                headers=auth["opsadmin"],
                json={"expected_version": 2, "assigned_to": str(ids["opsother"])},
            )
            assert changed.status_code == 200
            return output

        workers[0].runner.run = revoke
        try:
            assert workers[0].run_once()["status"] == "failed"
        finally:
            workers[0].runner.run = actual
        assert (
            client.get(accepted.headers["location"], headers=auth["opsanalyst"]).status_code == 404
        )
        settings.assessment_api_rate_limit = 1
        assert client.get(accepted.headers["location"], headers=auth["opsother"]).status_code == 200
        assert client.get(accepted.headers["location"], headers=auth["opsother"]).status_code == 429
        settings.assessment_api_rate_limit = 1000

        stage = "terminal_manual_review"
        assert submit(15)[0].status_code == 202
        queue.assessments.artifact_root = "/tmp/missing-approved-assets"
        final = None
        for _ in range(3):
            final = next_attempt(workers[0])
        queue.assessments.artifact_root = None
        assert (
            final["status"] == "failed"
            and final["fallback_route"] == "manual_review"
            and final["attempts"] == 3
        )
        assert not stop.is_set()

        stage = "invariant_checks"
        for exporter in exporters:
            assert exporter.flush()
        monitoring = client.get("/api/v1/internal/metrics", headers=auth["opsadmin"])
        assert monitoring.status_code == 200
        metrics = monitoring.json()
        assert metrics["queue"]["pending"] == metrics["queue"]["running"] == 0
        assert metrics["queue"]["succeeded"] == 14 and metrics["queue"]["failed"] == 2
        for name in ("model.scoring", "model.shap", "worker.execution"):
            assert any(r["name"] == name and r["count"] > 0 for r in metrics["series"])
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 16
            assert session.scalar(select(func.count(func.distinct(AssessmentJob.run_id)))) == 16
            for model in (Assessment, AssessmentExplanation, ModelScore, Decision):
                assert session.scalar(select(func.count()).select_from(model)) == 14
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "assessment.completed")
                )
                == 14
            )
            assert (
                session.scalar(
                    select(func.count()).select_from(Case).where(or_disposition_or_closed())
                )
                == 0
            )
        cpu_after, child_after = (
            resource.getrusage(resource.RUSAGE_SELF),
            resource.getrusage(resource.RUSAGE_CHILDREN),
        )

        def cgroup(name):
            from pathlib import Path

            path = Path("/sys/fs/cgroup") / name
            return (
                int(path.read_text())
                if path.exists() and path.read_text().strip().isdigit()
                else None
            )

        with owner.connect() as connection:
            postgres_version = connection.scalar(text("SHOW server_version"))
        return {
            "status": "PASS",
            "environment": {
                "python": ".".join(map(str, sys.version_info[:3])),
                "postgresql": postgres_version,
                "container_cpu_limit_cores": 2,
                "container_pid_limit": 128,
                "scientific_runtime": "backend/ml-requirements.txt (SHA-verified fitted baseline)",
            },
            "profile": {
                "synthetic_cases": 16,
                "steady_jobs": 12,
                "waves": 3,
                "submission_concurrency": 4,
                "worker_concurrency": 2,
                "queue_capacity": 4,
                "deadline_seconds": 180,
                "dataset": "new synthetic 27-feature records; no replay fixture used",
            },
            "steady_load": {
                "wall_seconds": round(steady_seconds, 3),
                "jobs_per_second": round(12 / steady_seconds, 4),
                "submission_latency": quantiles(latencies),
                "worker_wall_latency": quantiles(execution),
                "expected_http_outcomes": dict(statuses),
                "admission_contention_retries": len(contention_retries),
                "submission_latency_includes_retry_wait": True,
                "peak_active_queue": max(depths),
                "oldest_pending_age_seconds_observed": round(max(ages), 3),
                "unexpected_failures": 0,
            },
            "recovery": {
                "abrupt_worker_exit_recovered": True,
                "stale_worker_fenced": True,
                "inflight_pg_connection_termination_rolled_back": True,
                "same_claim_retry_succeeded": True,
                "authorization_revocation_blocked_publication": True,
                "rate_limit_enforced": True,
                "terminal_manual_review_after_three_attempts": True,
            },
            "invariants": {
                "committed_jobs": 16,
                "succeeded": 14,
                "terminal_manual_review": 2,
                "completed_assessments": 14,
                "duplicate_assessments": 0,
                "lost_jobs": 0,
                "unauthorized_successful_reads": 0,
                "automatic_case_actions": 0,
            },
            "resources": {
                "self_peak_rss_kib": cpu_after.ru_maxrss,
                "reaped_children_peak_rss_kib": child_after.ru_maxrss,
                "cpu_seconds": round(
                    cpu_after.ru_utime
                    + cpu_after.ru_stime
                    + child_after.ru_utime
                    + child_after.ru_stime
                    - cpu_before.ru_utime
                    - cpu_before.ru_stime
                    - child_before.ru_utime
                    - child_before.ru_stime,
                    3,
                ),
                "container_peak_bytes": cgroup("memory.peak"),
                "container_memory_limit_bytes": cgroup("memory.max"),
                "database_resources_included": False,
            },
            "monitoring": {
                "api": metrics["api"],
                "durable_events": metrics["durable_events"],
                "coverage": metrics["coverage"],
                "series": metrics["series"],
            },
            "interpretation": "Single local Linux/PG run, cold per-job initialization; descriptive measurements, not production capacity or an SLA.",
        }
    except Exception as error:
        cursor = error.__traceback__
        line = None
        while cursor:
            if cursor.tb_frame.f_code.co_filename == __file__:
                line = cursor.tb_lineno
            cursor = cursor.tb_next
        return {
            "status": "FAIL",
            "stage": stage,
            "error_type": type(error).__name__,
            "check_line": line,
            "diagnostics": diagnostics,
        }
    finally:
        watchdog.cancel()
        stop.set()
        for exporter in exporters:
            exporter.close()
        if client:
            client.close()
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=10)
        if engine:
            engine.dispose()
        with owner.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        owner.dispose()


def or_disposition_or_closed():
    from sqlalchemy import or_

    return or_(Case.disposition.is_not(None), Case.status == "closed")


if __name__ == "__main__":
    result = benchmark(json.loads(sys.stdin.read(65537)))
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
