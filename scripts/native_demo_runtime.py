"""Native demo launch glue around existing services. No provider activation or transport."""

import hashlib
import hmac
import json
import os
import platform
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid5

CONTROL = Path("/run/native")


def acceptance_passed(receipt, build_id):
    counts = receipt.get("required_test_counts") or {}
    clock = receipt.get("clock") or {}
    return (
        build_id != "unknown"
        and receipt.get("candidate_build_id") == build_id
        and receipt.get("expected_schema") == "0023_durable_regulatory_start"
        and receipt.get("pytest_exit_code") == 0
        and counts.get("total", 0) > 0
        and all(counts.get(k) == 0 for k in ("skipped", "failed", "errors"))
        and clock.get("samples", 0) > 10
        and all(
            clock.get(k) == 0
            for k in ("host_backsteps", "database_backsteps", "database_outside_host_roundtrip")
        )
        and clock.get("sampler_errors") == []
        and receipt.get("provider_requests") == 0
    )


def load_environment(path):
    value = json.loads(path.read_text())
    allowed = {
        "DATABASE_URL",
        "APP_ENV",
        "JWT_SECRET",
        "ACCESS_TOKEN_MINUTES",
        "CSV_STAGING_ROOT",
        "BATCH_ASSESSMENT_DISPATCH_ENABLED",
        "INVESTIGATION_SIMULATION_ENABLED",
        "INVESTIGATION_EXTERNAL_ENABLED",
        "ANTHROPIC_SYNTHETIC_DEMO_ENABLED",
        "ANTHROPIC_ANALYST_GENERATION_ENABLED",
        "REGULATORY_INVESTIGATION_ENABLED",
    }
    if set(value) - allowed - {"native_worker_token"}:
        raise ValueError("unreviewed_runtime_setting")
    # This portable preparation has no live-provider activation capability.
    for key in allowed:
        if (
            key.endswith("_ENABLED")
            and key != "BATCH_ASSESSMENT_DISPATCH_ENABLED"
            and value.get(key) != "false"
        ):
            raise ValueError("separate_provider_or_source_activation_required")
    keep = {
        k: v
        for k, v in os.environ.items()
        if k
        in {
            "PATH",
            "HOME",
            "LANG",
            "NUMBA_CACHE_DIR",
            "MPLCONFIGDIR",
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
        }
    }
    os.environ.clear()
    os.environ.update(keep)
    os.environ.update({k: v for k, v in value.items() if k in allowed})
    return value


def connection():
    from app.core.release_metadata import load_identity
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    if platform.system() != "Linux" or any(
        s in platform.release().lower() for s in ("microsoft", "wsl")
    ):
        raise ValueError("native_linux_required")
    state = json.loads((CONTROL / "control.json").read_text())
    url = make_url(os.environ["DATABASE_URL"])
    if (
        url.host != "db"
        or url.database != state["database"]
        or not url.database.startswith("tf_native_demo_")
        or url.query
    ):
        raise ValueError("isolated_database_required")
    identity = load_identity()
    if not acceptance_passed(
        json.loads((CONTROL / "acceptance.json").read_text()), identity["build_id"]
    ):
        raise ValueError("native_acceptance_required")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as c:
        if (
            str(c.scalar(text("SELECT system_identifier FROM pg_control_system()")))
            != (CONTROL / "cluster-id").read_text().strip()
        ):
            raise ValueError("cluster_identity_mismatch")
        if c.scalar(text("SELECT current_database()")) != state["database"]:
            raise ValueError("database_identity_mismatch")
    return engine


def current_clock(engine):
    from app.core.release import require_compatible
    from app.services.snapshot_clock import SnapshotTime

    require_compatible(engine)
    observed = SnapshotTime(engine).observe()
    print(json.dumps({"clock": "guard_passed", "epoch": observed.epoch}), flush=True)


def actor(engine, username):
    from app.models import User
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        user = session.scalar(
            select(User).where(
                User.username == username, User.active.is_(True), User.role == "admin"
            )
        )
        if user is None:
            raise ValueError("active_admin_required")
        return user.id


def register(engine, admin):
    from app.core.config import Settings
    from app.models import AssessmentWorker, CSVImportWorker
    from app.services.assessment_jobs import AssessmentJobService
    from app.services.csv_imports import CSVImportService
    from app.services.investigation_coordinator import InvestigationCoordinator
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    # Resume partial setup only for the exact active identity; never rotate/reactivate.
    settings = Settings(_env_file=None)
    for role, service, model in (
        ("assessment-worker", AssessmentJobService(engine), AssessmentWorker),
        ("import-worker", CSVImportService(engine, settings), CSVImportWorker),
    ):
        token = json.loads((CONTROL / f"{role}.json").read_text())["native_worker_token"]
        with Session(engine) as session:
            prior = session.scalar(select(model).where(model.name == "native-" + role))
            if prior is not None:
                if not (
                    prior.active
                    and prior.provisioned_by == admin
                    and hmac.compare_digest(
                        prior.token_sha256, hashlib.sha256(token.encode()).hexdigest()
                    )
                ):
                    raise ValueError("worker_identity_conflict")
                continue
        service.register_worker(admin_id=admin, name="native-" + role, token=token)
    InvestigationCoordinator(engine, settings).register_worker(
        admin,
        "native-investigation",
        Path("/run/secrets/investigation_worker_token").read_text().strip(),
    )
    print(json.dumps({"workers_registered": True}), flush=True)


def fixtures(engine, admin):
    from app.core.config import Settings
    from app.services.assessment_jobs import AssessmentJobService
    from app.services.connected_scenarios import scenario_bundle
    from app.services.evidence import EvidenceService
    from app.services.evidence_read import EvidenceReadService

    foundation, queue = EvidenceService(engine), AssessmentJobService(engine)
    reader = EvidenceReadService(engine, Settings(_env_file=None))
    for key in ("ordinary", "velocity", "incomplete_history"):
        bundle = scenario_bundle(key)
        source = foundation.register_source(admin, bundle.scenario_id)
        release = foundation.admit_version(admin, source, bundle)
        case = foundation.create_case(admin, release)
        context = reader.get_case_context(
            admin, case
        )  # Fresh authorized snapshot, not a fabricated token.
        run = uuid5(bundle.scenario_id, "native-demo:Coverage:v1")
        job, _ = queue.enqueue(
            actor_id=admin,
            case_id=case,
            expected_version=context.snapshot.case_version,
            run_id=run,
            idempotency_key="native_" + run.hex,
            policy="Coverage",
            request_audit=True,
        )
        print(
            json.dumps(
                {
                    "scenario": key,
                    "case_id": str(case),
                    "source_id": str(source),
                    "job_id": str(job["job_id"]),
                    "synthetic": True,
                    "browser_path": f"/#/cases/{case}/investigation",
                }
            ),
            flush=True,
        )


def main():
    role, *args = sys.argv[1:]
    config = load_environment(CONTROL / "settings.json")
    engine = connection()
    try:
        if role == "operator":
            action, *values = args
            if action == "migrate" and not values:
                subprocess.run(["alembic", "upgrade", "0023_durable_regulatory_start"], check=True)
                current_clock(engine)
            elif action == "bootstrap" and len(values) == 2:
                current_clock(engine)
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.security.bootstrap",
                        "--username",
                        values[0],
                        "--role",
                        values[1],
                    ],
                    check=True,
                )
            elif action in {"register-workers", "fixtures"} and len(values) == 1:
                current_clock(engine)
                admin = actor(engine, values[0])
                (register if action == "register-workers" else fixtures)(engine, admin)
            elif action == "status" and not values:
                current_clock(engine)
            else:
                raise ValueError("unsupported_operator_command")
            return
        current_clock(engine)
    finally:
        engine.dispose()
    if role == "api":
        os.execvp(
            "uvicorn",
            [
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            ],
        )
    if role in {"assessment-worker", "import-worker"}:
        file = Path("/tmp/worker-token-" + secrets.token_hex(8))
        file.write_text(config["native_worker_token"])
        file.chmod(0o600)
        module = "assessment_worker" if role == "assessment-worker" else "csv_import_worker"
        os.execv(
            sys.executable,
            [sys.executable, "-B", "-m", "app.workers." + module, "--token-file", str(file)],
        )
    if role in {"evidence-worker", "draft-worker"}:
        module = (
            "investigation_worker" if role == "evidence-worker" else "investigation_draft_worker"
        )
        while True:
            subprocess.run(
                [sys.executable, "-B", "-m", "app.workers." + module, "--max-jobs", "1"], check=True
            )
            time.sleep(2)
    else:
        raise ValueError("unsupported_worker_role")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {"status": "blocked", "error_type": type(error).__name__, "provider_requests": 0}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
