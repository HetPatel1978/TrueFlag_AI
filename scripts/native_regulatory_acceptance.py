"""Offline-provider acceptance on an operator-supplied native Linux/PostgreSQL runner.

Never provisions a host, reads .env, activates providers, or migrates a demo database.
Candidate release metadata is installed only in a temporary test source copy.
"""

import argparse
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0023_durable_regulatory_start"


def native_linux(system=None, kernel=None):
    system = platform.system() if system is None else system
    kernel = platform.release() if kernel is None else kernel
    if system != "Linux" or any(word in kernel.lower() for word in ("microsoft", "wsl")):
        raise RuntimeError("independent_native_linux_required")


def required_test_counts(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    return {
        "total": len(cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
        "failed": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-file", type=Path, required=True)
    parser.add_argument("--expected-cluster-file", type=Path, required=True)
    parser.add_argument("--synchronization-evidence-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    native_linux()  # Refuse Windows/WSL before opening credentials or connecting.
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("pinned_python_311_required")
    if args.database_url_file.stat().st_mode & 0o077:
        raise RuntimeError("private_database_url_file_required")
    if args.synchronization_evidence_file.read_text().strip() != "yes":
        raise RuntimeError("operator_host_synchronization_evidence_required")
    if not 0 <= time.time() - args.synchronization_evidence_file.stat().st_mtime <= 300:
        raise RuntimeError("fresh_host_synchronization_evidence_required")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(args.database_url_file.read_text().strip())
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"db", "127.0.0.1", "localhost"}
        or not (url.database or "").startswith("tf_acceptance_")
        or url.query
    ):
        raise RuntimeError("new_isolated_acceptance_database_required")
    expected = args.expected_cluster_file.read_text().strip()
    engine = create_engine(
        url, connect_args={"connect_timeout": 5, "options": "-cstatement_timeout=2000"}
    )
    with engine.connect() as c:
        actual = str(c.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        if actual != expected or c.scalar(text("SELECT current_database()")) != url.database:
            raise RuntimeError("isolated_cluster_identity_mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    stop, errors = threading.Event(), []
    observations = []

    def sample():
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
                c.execute(text("SET default_transaction_read_only=on"))
                while not stop.is_set():
                    before = time.time_ns()
                    db = int(
                        c.scalar(text("SELECT extract(epoch FROM clock_timestamp())"))
                        * 1_000_000_000
                    )
                    after = time.time_ns()
                    observations.append(
                        (before, after, db, time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW))
                    )
                    if len(observations) > 15000:
                        raise RuntimeError("bounded_observation_limit")
                    stop.wait(0.2)
        except Exception as error:
            errors.append(type(error).__name__)

    def counts():
        return dict(
            samples=len(observations),
            host_backsteps=sum(b[0] < a[0] for a, b in zip(observations, observations[1:])),
            database_backsteps=sum(b[2] < a[2] for a, b in zip(observations, observations[1:])),
            database_outside_host_roundtrip=sum(
                not before <= db <= after for before, after, db, _ in observations
            ),
            sampler_errors=errors[:10],
        )

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    result = None
    test_counts = None
    try:
        # Two idle observation windows; continue independent sampling through tests.
        for _ in range(2):
            stop.wait(60)
            print(json.dumps({"clock_window": counts(), "provider_requests": 0}), flush=True)
            if any(v for k, v in counts().items() if k != "samples") or len(observations) < 10:
                raise RuntimeError("clock_observation_failed")
        with tempfile.TemporaryDirectory(prefix="trueflag-native-test-") as temporary:
            tree = Path(temporary)
            for directory in ("backend", "scripts", "contracts"):
                shutil.copytree(
                    ROOT / directory,
                    tree / directory,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", ".pytest_cache", "_release.json", ".env", ".env.*"
                    ),
                )
            for name in (
                "0020_claude_provider.py",
                "0021_regulatory_draft_bindings.py",
                "0022_claude_development_scope.py",
                "0023_durable_regulatory_start.py",
            ):
                shutil.copyfile(
                    tree / "backend/alembic/candidates" / name,
                    tree / "backend/alembic/versions" / name,
                )
            (tree / "backend/app/core/schema.py").write_text(
                f'EXPECTED_SCHEMA_REVISION = "{REVISION}"\n'
            )
            # Explicitly unknown test build; never fabricate a production release identity.
            sys.path.insert(0, str(ROOT / "backend"))
            from app.core.release_metadata import unknown_identity

            identity = unknown_identity()
            identity["expected_schema_revision"] = REVISION
            (tree / "backend/app/_release.json").write_text(json.dumps(identity))
            child_env = {
                key: os.environ[key]
                for key in ("PATH", "HOME", "LANG", "TMPDIR")
                if key in os.environ
            }
            child_env.update(
                PYTHONPATH=str(tree / "backend"),
                DATABASE_URL=url.render_as_string(hide_password=False),
                TRUEFLAG_TEST_POSTGRES_URL=url.render_as_string(hide_password=False),
                JWT_SECRET=secrets.token_urlsafe(48),
                OPENBLAS_NUM_THREADS="1",
                OMP_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
            )
            tests = [
                "test_deferred_regulatory_start_postgres.py",
                "test_regulatory_investigation.py",
                "test_snapshot_clock_integrity.py",
                "test_snapshot_clock_policy.py",
                "test_clock_health.py",
            ]
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    *["backend/tests/" + name for name in tests],
                    "-q",
                    "--tb=short",
                    "-p",
                    "no:cacheprovider",
                    "--junitxml=" + str(tree / "acceptance-junit.xml"),
                ],
                cwd=tree,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            test_counts = required_test_counts(tree / "acceptance-junit.xml")
            output = result.stdout + result.stderr
            for value in (url.render_as_string(hide_password=False), url.password):
                if value:
                    output = output.replace(value, "[database credential redacted]")
            (args.output / "pytest.txt").write_text(output)
            print(output)
    finally:
        stop.set()
        thread.join(5)
        report = {
            "clock": counts(),
            "observations": observations,
            "kernel": platform.release(),
            "operator_supplied_sync_evidence": True,
            "expected_schema": REVISION,
            "pytest_exit_code": None if result is None else result.returncode,
            "required_test_counts": test_counts,
            "provider_requests": 0,
            "live_dispatch_authorized": False,
            "candidate_build_id": json.loads((ROOT / "backend/app/_release.json").read_text()).get(
                "build_id", "unknown"
            )
            if (ROOT / "backend/app/_release.json").exists()
            else "unknown",
        }
        if len(observations) > 1:
            wall = (observations[-1][0] - observations[0][0]) / 1e9
            raw = (observations[-1][3] - observations[0][3]) / 1e9
            report["clock_rate_review"] = {
                "host_wall_seconds": wall,
                "host_raw_monotonic_seconds": raw,
                "wall_raw_ratio": wall / raw if raw > 0 else None,
                "operator_review_required": True,
            }
        (args.output / "evidence.json").write_text(json.dumps(report, indent=2))
        engine.dispose()
    return (
        0
        if result
        and result.returncode == 0
        and test_counts
        and test_counts["total"] > 0
        and not any(test_counts[k] for k in ("skipped", "failed", "errors"))
        and not any(v for k, v in counts().items() if k != "samples")
        else 1
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        allowed = {
            "independent_native_linux_required",
            "pinned_python_311_required",
            "private_database_url_file_required",
            "operator_host_synchronization_evidence_required",
            "fresh_host_synchronization_evidence_required",
            "new_isolated_acceptance_database_required",
            "isolated_cluster_identity_mismatch",
            "clock_observation_failed",
        }
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(error).__name__,
                    "code": str(error)
                    if str(error) in allowed
                    else "native_acceptance_unavailable",
                    "provider_requests": 0,
                }
            )
        )
        raise SystemExit(1) from None
