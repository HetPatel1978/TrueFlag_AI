"""Bounded real Linux/PG/TCP CSV benchmark. Only aggregate observations leave the fixture."""

import csv
import hashlib
import io
import json
import logging
import os
import resource
import secrets
import socket
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import uvicorn
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.database import make_engine
from app.main import create_app
from app.models import (
    Alert,
    Assessment,
    AssessmentExplanation,
    AssessmentJob,
    AuditEvent,
    BatchAssessment,
    BatchAssessmentItem,
    Case,
    CSVImportRow,
    Decision,
    ModelScore,
    User,
)
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.schemas.csv_uploads import COLUMNS
from app.security.auth import password_hash
from app.services.assessment_jobs import AssessmentJobService
from app.services.csv_imports import CSVImportService
from app.workers.assessment_worker import AssessmentWorker
from app.workers.csv_import_worker import CSVImportWorker
from benchmark_operations import headers, quantiles
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema


def cgroup(name):
    value = (Path("/sys/fs/cgroup") / name).read_text().strip()
    return int(value) if value.isdigit() else None


def cpu_seconds():
    return sum(
        r.ru_utime + r.ru_stime
        for r in (
            resource.getrusage(resource.RUSAGE_SELF),
            resource.getrusage(resource.RUSAGE_CHILDREN),
        )
    )


def synthetic(size, prefix):
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["Annual Income" if c == "income" else c for c in COLUMNS])
    for n in range(size):
        row = {name: "0" for name in COLUMNS}
        row.update(
            source_id=f"synthetic-load-{prefix}-{n}",
            data_classification="synthetic",
            feature_contract_version=FEATURE_CONTRACT_VERSION,
            state="QZ",
            kycRiskScore=str(n % 6),
            income="" if n % 2 else "0",
            totalSpend90d=str(10 + n),
        )
        if n >= size - 2:
            row["income"] = "=SYNTHETIC_REJECTED_CANARY()"
        writer.writerow([row[name] for name in COLUMNS])
    return out.getvalue().encode("utf-8")


class CanaryLogCheck(logging.Handler):
    def __init__(self):
        super().__init__()
        self.leaks = 0

    def emit(self, record):
        # Inspect but never retain/print log contents, credentials or customer-like cells.
        if "SYNTHETIC_REJECTED_CANARY" in str(record.__dict__):
            self.leaks += 1


def benchmark(config):
    assert (
        sys.platform == "linux"
        and make_url(config["database_url"]).get_backend_name() == "postgresql"
    )
    owner = make_engine(config["database_url"])
    identity = "tf_batch_acceptance_" + uuid4().hex
    with owner.begin() as connection:
        connection.execute(CreateSchema(identity))
    url = make_url(config["database_url"]).update_query_dict(
        {"options": f"-csearch_path={identity} -capplication_name={identity}"}
    )
    database_url = url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = database_url
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    engine = client = server = server_thread = None
    stop = threading.Event()
    watchdog = threading.Timer(3600, stop.set)
    watchdog.daemon = True
    watchdog.start()
    threads = []
    stage = "setup"
    report = {"status": "FAIL", "workloads": []}
    log_check = CanaryLogCheck()
    logging.getLogger().addHandler(log_check)
    lock = threading.Lock()
    execution, api_times, statuses, worker_errors = [], defaultdict(list), Counter(), Counter()
    try:
        command.upgrade(Config("backend/alembic.ini"), "head")
        # Keep default parser/import/export/rate limits; small queue deliberately exercises pressure.
        settings = Settings(
            csv_staging_root=Path("/tmp/batch-load-csv"),
            assessment_queue_capacity=20,
            batch_assessment_dispatch_enabled=True,
        )
        engine = make_engine(database_url)
        with Session(engine) as session, session.begin():
            user = User(
                username="batchloadadmin",
                role="admin",
                password_hash=password_hash.hash(secrets.token_urlsafe(24)),
            )
            session.add(user)
            session.flush()
            actor_id = user.id
            # In-memory synthetic issuer; real JWT validation/current SQL permissions remain enabled.
            actor = type("SyntheticActor", (), {"id": actor_id})()
        queue = AssessmentJobService(engine)
        token = secrets.token_hex(32)
        queue.register_worker(admin_id=actor_id, name="batch-load-ml-worker", token=token)
        imports = CSVImportService(engine, settings)
        import_token = secrets.token_hex(32)
        imports.register_worker(actor_id, "batch-load-import-worker", import_token)
        workers = [AssessmentWorker(queue, token, stop) for _ in range(2)]
        importer = CSVImportWorker(imports, import_token)
        app = create_app(settings, engine)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(app, log_config=None, access_log=False, log_level="error")
        )
        server_thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        server_thread.start()
        deadline = time.monotonic() + 20
        while not server.started and time.monotonic() < deadline:
            stop.wait(0.05)
        assert server.started
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)

        def request(method, path, name, *, expected=(200,), **kwargs):
            extra_headers = kwargs.pop("headers", {})
            for attempt in range(12):
                if stop.is_set():
                    raise RuntimeError("benchmark_deadline")
                started = time.monotonic()
                response = client.request(
                    method,
                    path,
                    headers={**headers(actor, settings), **extra_headers},
                    **kwargs,
                )
                elapsed = (time.monotonic() - started) * 1000
                with lock:
                    api_times[name].append(elapsed)
                    statuses[str(response.status_code)] += 1
                if response.status_code == 429 and attempt < 11:
                    stop.wait(min(60, max(1, int(response.headers.get("retry-after", "5")))))
                    continue
                assert response.status_code in expected, f"{name}_http_{response.status_code}"
                assert "SYNTHETIC_REJECTED_CANARY" not in response.text
                return response
            raise AssertionError("request_retries_exhausted")

        def process(worker, name):
            while not stop.is_set():
                started = time.monotonic()
                try:
                    value = worker.run_once()
                    if name == "ml" and value is not None:
                        with lock:
                            execution.append((time.monotonic() - started) * 1000)
                            worker_errors[value["status"]] += 1
                    if value is None:
                        stop.wait(0.1)
                except Exception:
                    with lock:
                        worker_errors[name + "_exception"] += 1
                    stop.wait(0.2)

        for worker, name in [(importer, "import"), *[(w, "ml") for w in workers]]:
            thread = threading.Thread(target=process, args=(worker, name), daemon=True)
            thread.start()
            threads.append(thread)

        stage = "unsupported_5000_rows"
        response = request(
            "POST",
            "/api/v1/batch-uploads",
            "oversized_upload",
            expected=(413,),
            content=synthetic(5000, uuid4().hex),
            headers={"Content-Type": "text/csv", "Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 413
        report["unsupported_5000"] = {
            "http_status": 413,
            "configured_row_limit": settings.csv_max_rows,
            "limits_raised": False,
        }

        for size in (10,) if config.get("smoke") else (100, 1000):
            stage = f"workload_{size}"
            wall, cpu = time.monotonic(), cpu_seconds()
            execution_start = len(execution)
            resource_samples, depths, ages, connection_samples = [], [], [], []

            def sample():
                resource_samples.append(cgroup("memory.current"))
                with engine.connect() as connection:
                    pending, running, age = connection.execute(
                        text(
                            "SELECT count(*) FILTER (WHERE status='pending'), count(*) FILTER (WHERE status='running'), "
                            "coalesce(extract(epoch from clock_timestamp()-min(created_at) FILTER (WHERE status='pending')),0) FROM assessment_jobs"
                        )
                    ).one()
                    connections, active = connection.execute(
                        text(
                            "SELECT count(*),count(*) FILTER (WHERE state='active') FROM pg_stat_activity WHERE application_name=:app"
                        ),
                        {"app": identity},
                    ).one()
                depths.append(pending + running)
                ages.append(float(age))
                connection_samples.append((connections, active))

            content = synthetic(size, uuid4().hex)
            start = time.monotonic()
            upload = request(
                "POST",
                "/api/v1/batch-uploads",
                "upload",
                expected=(201,),
                content=content,
                headers={"Content-Type": "text/csv", "Idempotency-Key": uuid4().hex},
            ).json()
            upload_seconds = time.monotonic() - start
            uid = upload["upload_id"]
            mapping = {c: "Annual Income" if c == "income" else c for c in COLUMNS}
            start = time.monotonic()
            preview = request(
                "POST",
                f"/api/v1/batch-uploads/{uid}/validations",
                "validation",
                expected=(201,),
                json={"mapping": mapping, "units": "baseline_source_units"},
            ).json()
            validation_seconds = time.monotonic() - start
            assert (
                preview["total_rows"] == size
                and preview["valid_rows"] == size - 2
                and preview["invalid_rows"] == 2
            )
            vid = preview["validation_id"]
            approval = {
                n: preview[n]
                for n in (
                    "upload_sha256",
                    "mapping_sha256",
                    "mapping_version",
                    "validator_version",
                    "units",
                )
            }
            approval.update(approve_valid_rows=True, validation_version=preview["version"])
            path = f"/api/v1/batch-uploads/{uid}/validations/{vid}/imports"
            key = uuid4().hex
            start = time.monotonic()
            with ThreadPoolExecutor(max_workers=4) as pool:
                receipts = list(
                    pool.map(
                        lambda _: request(
                            "POST",
                            path,
                            "import_approval",
                            expected=(202,),
                            json=approval,
                            headers={"Idempotency-Key": key},
                        ).json(),
                        range(4),
                    )
                )
            assert len({r["import_id"] for r in receipts}) == 1
            iid = receipts[0]["import_id"]
            while not stop.is_set():
                sample()
                imported = request("GET", f"/api/v1/batch-imports/{iid}", "import_status").json()
                if imported["status"] not in ("pending", "running"):
                    break
                stop.wait(1)
            import_seconds = time.monotonic() - start
            assert (
                imported["status"] == "partially_completed" and imported["created_rows"] == size - 2
            )
            assert imported["excluded_rows"] == 2 and imported["processed_rows"] == size
            with Session(engine) as session:
                assert session.scalar(select(func.count()).select_from(AssessmentJob)) == sum(
                    w["assessed"] for w in report["workloads"]
                )
            start = time.monotonic()
            batch_key = uuid4().hex
            intent = {
                "start_assessment": True,
                "import_validation_sha256": imported["validation_sha256"],
                "policy": "Coverage",
            }
            batch = request(
                "POST",
                f"/api/v1/batch-imports/{iid}/assessments",
                "assessment_start",
                expected=(202,),
                json=intent,
                headers={"Idempotency-Key": batch_key},
            ).json()
            bid = batch["batch_id"]
            last_reported = -1
            while not stop.is_set():
                sample()
                batch = request("GET", f"/api/v1/batch-assessments/{bid}", "batch_status").json()
                assert batch["total_cases"] == sum(
                    batch[k]
                    for k in (
                        "pending_dispatch",
                        "queued",
                        "running",
                        "succeeded",
                        "failed_manual_review",
                        "skipped",
                    )
                )
                if batch["succeeded"] // 50 != last_reported:
                    last_reported = batch["succeeded"] // 50
                    print(
                        json.dumps(
                            {
                                "event": "progress",
                                "records": size,
                                "succeeded": batch["succeeded"],
                                "elapsed_seconds": round(time.monotonic() - start, 1),
                            }
                        ),
                        flush=True,
                    )
                if batch["status"] not in ("dispatching", "processing"):
                    break
                stop.wait(5)
            assessment_seconds = time.monotonic() - start
            assert batch["status"] == "completed" and batch["succeeded"] == size - 2
            assert batch["failed_manual_review"] == batch["retrying"] == batch["skipped"] == 0
            # Compare every bounded API page, history/provenance, canonical links and CSV row.
            results = {}
            for offset in range(0, size - 2, 25):
                page = request(
                    "GET",
                    f"/api/v1/batch-assessments/{bid}/results?offset={offset}&limit=25",
                    "results",
                ).json()
                for item in page["items"]:
                    value = item["assessment"]
                    assert (
                        item["outcome"] == "succeeded" and value["human_decision_required"] is True
                    )
                    assert (
                        value["model_sha256"] == batch["model_sha256"]
                        and value["policy_version"] == batch["policy_version"]
                    )
                    assert (
                        value["explanation"]["status"] == "verified"
                        and len(value["explanation"]["features"]) == 27
                    )
                    assert (
                        abs(
                            value["explanation"]["base_value"]
                            + sum(f["contribution"] for f in value["explanation"]["features"])
                            - value["score"]
                        )
                        <= 1e-6
                    )
                    assert item["case_id"] not in results
                    results[item["case_id"]] = value
            assert len(results) == size - 2
            exported = {}
            for offset in range(0, size - 2, 500):
                response = request(
                    "GET",
                    f"/api/v1/batch-assessments/{bid}/export?offset={offset}&limit=500",
                    "export",
                )
                for row in csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))):
                    assert row["case_id"] not in exported
                    exported[row["case_id"]] = row
                    assert float(row["sar_positive_score"]) == results[row["case_id"]]["score"]
                    assert row["recommendation"] == results[row["case_id"]]["recommended_route"]
                    assert row["model_sha256"] == results[row["case_id"]]["model_sha256"]
                with Session(engine) as session:
                    audit = session.scalars(
                        select(AuditEvent)
                        .where(
                            AuditEvent.action == "batch.assessment.exported",
                            AuditEvent.resource_id == bid,
                        )
                        .order_by(AuditEvent.created_at.desc())
                    ).first()
                    assert audit.details["sha256"] == hashlib.sha256(response.content).hexdigest()
            assert results.keys() == exported.keys()
            case_id = next(iter(results))
            overview = request("GET", f"/api/v1/cases/{case_id}/overview", "case_overview").json()
            assert overview["assessment_status"] == "succeeded"
            history = request("GET", f"/api/v1/cases/{case_id}/assessments", "history").json()
            assert (
                history["total"] == 1
                and history["items"][0]["assessment_id"] == results[case_id]["assessment_id"]
            )
            replay = request(
                "POST",
                f"/api/v1/batch-imports/{iid}/assessments",
                "assessment_replay",
                expected=(202,),
                json=intent,
                headers={"Idempotency-Key": batch_key},
            ).json()
            assert replay["batch_id"] == bid
            with Session(engine) as session:
                rows = session.execute(
                    select(CSVImportRow, Case, Alert)
                    .join(Case, Case.id == CSVImportRow.case_id)
                    .join(Alert, Alert.id == Case.alert_id)
                    .where(CSVImportRow.import_id == UUID(iid))
                ).all()
                assert len(rows) == size - 2
                for row, case, alert in rows:
                    assert (
                        row.alert_id == alert.id
                        and case.status == "open"
                        and case.disposition is None
                    )
                    assert alert.feature_contract_version == FEATURE_CONTRACT_VERSION and set(
                        alert.features
                    ) == set(AlertFeatures.model_fields)
                    assert alert.features["income"] == (None if (row.row_number - 2) % 2 else 0)
                expected = size - 2 + sum(w["assessed"] for w in report["workloads"])
                for model in (
                    Alert,
                    Case,
                    Assessment,
                    AssessmentExplanation,
                    AssessmentJob,
                    ModelScore,
                    Decision,
                ):
                    assert session.scalar(select(func.count()).select_from(model)) == expected
                # Legacy decisions table stores model recommendations, not human dispositions.
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(Decision)
                        .where(
                            Decision.route.not_in(
                                ("retain_human_review", "review_reduction_candidate")
                            )
                        )
                    )
                    == 0
                )
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(AssessmentJob)
                        .where(AssessmentJob.attempts != 1)
                    )
                    == 0
                )
                stored_batch = session.get(BatchAssessment, UUID(bid))
                backpressure = stored_batch.backpressure_count
                job_times = session.execute(
                    select(AssessmentJob.created_at, Assessment.created_at)
                    .select_from(AssessmentJob)
                    .join(BatchAssessmentItem, BatchAssessmentItem.job_id == AssessmentJob.id)
                    .join(Assessment, Assessment.id == AssessmentJob.assessment_id)
                    .where(BatchAssessmentItem.batch_id == UUID(bid))
                ).all()
                dispatch_seconds = (
                    max(created for created, _ in job_times) - stored_batch.created_at
                ).total_seconds()
                queued_to_completion = [
                    (processed - created).total_seconds() * 1000 for created, processed in job_times
                ]
            assert max(depths) <= 20 and not log_check.leaks
            elapsed = time.monotonic() - wall
            row = {
                "records": size,
                "valid_imported": size - 2,
                "rejected": 2,
                "assessed": size - 2,
                "skipped": 0,
                "duplicate_assessments": 0,
                "lost_jobs": 0,
                "failures": 0,
                "retries": 0,
                "upload_seconds": round(upload_seconds, 3),
                "validation_seconds": round(validation_seconds, 3),
                "import_seconds": round(import_seconds, 3),
                "assessment_seconds": round(assessment_seconds, 3),
                "assessment_records_per_second": round((size - 2) / assessment_seconds, 4),
                "accepted_to_last_job_seconds": round(dispatch_seconds, 3),
                "dispatch_jobs_per_second_including_backpressure": round(
                    (size - 2) / max(0.001, dispatch_seconds), 4
                ),
                "queued_to_persisted_latency": quantiles(queued_to_completion),
                "workflow_seconds": round(elapsed, 3),
                "worker_wall_latency": quantiles(execution[execution_start:]),
                "queue_depth_peak": max(depths),
                "oldest_pending_age_peak_seconds": round(max(ages), 3),
                "backpressure_events": backpressure,
                "memory_current_peak_bytes": max(resource_samples),
                "cpu_seconds_self_and_reaped_children": round(cpu_seconds() - cpu, 3),
                "cpu_utilization_pct_of_two_core_limit": round(
                    (cpu_seconds() - cpu) / elapsed / 2 * 100, 2
                ),
                "db_connections_peak": max(c[0] for c in connection_samples),
                "db_active_connections_peak": max(c[1] for c in connection_samples),
            }
            report["workloads"].append(row)
            print(json.dumps({"event": "workload_complete", **row}), flush=True)
        assert not worker_errors.get("import_exception", 0) and not worker_errors.get(
            "ml_exception", 0
        )
        report.update(
            status="PASS",
            environment={
                "python": ".".join(map(str, sys.version_info[:3])),
                "cpus": 2,
                "memory_limit_bytes": cgroup("memory.max"),
                "container_memory_peak_bytes": cgroup("memory.peak"),
                "worker_concurrency": 2,
                "queue_capacity": 20,
                "api_rate_limit_per_minute": settings.assessment_api_rate_limit,
                "deadline_seconds": 3600,
                "default_parser_and_import_limits_unchanged": True,
                "database_cpu_memory_excluded": True,
                "db_sampling_seconds": "1 during import; 5 during assessment",
            },
            api_latency={key: quantiles(value) for key, value in api_times.items()},
            http_status_counts=dict(statuses),
            worker_outcomes=dict(worker_errors),
            sensitive_log_leaks=log_check.leaks,
            interpretation="Single local synthetic run with cold per-case RF/SHAP children; descriptive baseline, not production capacity or certification.",
        )
        return report
    except Exception as error:
        cursor, line = error.__traceback__, None
        while cursor:
            if cursor.tb_frame.f_code.co_filename == __file__:
                line = cursor.tb_lineno
            cursor = cursor.tb_next
        return {
            **report,
            "status": "FAIL",
            "stage": stage,
            "error_type": type(error).__name__,
            "check_line": line,
        }
    finally:
        stop.set()
        watchdog.cancel()
        for thread in threads:
            thread.join(timeout=40)
        if client:
            client.close()
        if server:
            server.should_exit = True
        if server_thread:
            server_thread.join(timeout=10)
        if engine:
            engine.dispose()
        logging.getLogger().removeHandler(log_check)
        with owner.begin() as connection:
            connection.execute(DropSchema(identity, cascade=True))
        owner.dispose()


if __name__ == "__main__":
    output = benchmark(json.loads(sys.stdin.read(65537)))
    print(json.dumps({"event": "report", **output}), flush=True)
    raise SystemExit(0 if output["status"] == "PASS" else 1)
