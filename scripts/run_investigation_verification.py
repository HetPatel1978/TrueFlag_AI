"""Pinned Linux/PG investigation acceptance in disposable schemas on the recovery clone."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


class Results:
    def pytest_terminal_summary(self, terminalreporter):
        stats = terminalreporter.stats
        print(
            "\nINVESTIGATION_TEST_COUNTS:"
            + json.dumps(
                {
                    "passed": len(stats.get("passed", [])),
                    "failed": len(stats.get("failed", [])) + len(stats.get("error", [])),
                    "skipped": len(stats.get("skipped", [])),
                }
            )
        )


def inside():
    import pytest
    from sqlalchemy.engine import make_url

    payload = json.loads(sys.stdin.read(65537))
    url = make_url(payload["database_url"])
    if url.host != "db" or not url.database.startswith("tf_reference_gate_clone_"):
        raise RuntimeError("isolated_clone_required")
    os.environ.update(
        DATABASE_URL=payload["database_url"],
        TRUEFLAG_TEST_POSTGRES_URL=payload["database_url"],
        TRUEFLAG_TEST_REAL_ASSESSMENT="1",
        JWT_SECRET=secrets.token_urlsafe(48),
    )
    paths = (
        ["backend/tests"]
        if payload["full"]
        else ["backend/tests/test_investigation_coordinator.py"]
    )
    if payload.get("drafts") and not payload["full"]:
        paths = ["backend/tests/test_investigation_drafts.py"]
    return pytest.main(
        [
            *paths,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            "/tmp/investigation-tests",
        ],
        plugins=[Results()],
    )


def main(full, drafts=False):
    from app.core.config import Settings
    from sqlalchemy.engine import make_url

    recovery = json.loads((ROOT / "runtime/phase3-4-approval-migration.json").read_bytes())
    assert recovery["status"] == "PASS"
    directory = (ROOT / recovery["private_recovery_directory"]).resolve(strict=True)
    assert directory.is_relative_to((ROOT / "runtime").resolve())
    name = json.loads((directory / "recovery-manifest.json").read_bytes())["clone_database"]
    original = make_url(Settings().database_url)
    assert (
        original.host in {"127.0.0.1", "localhost"}
        and name.startswith("tf_reference_gate_clone_")
        and name != original.database
    )
    url = original.set(database=name, host="db", port=5432)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "trueflag-ai_default",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "3g",
        "--cpus",
        "2",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
    ]
    for key in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
        command.extend(["-e", key + "=1"])
    for relative in [
        "backend",
        "scripts",
        "contracts",
        "assets/local/regulatory/proposed",
        "assets/local/regulatory/research_v2",
        "assets/local/baseline",
        "assets/local/explanation_reference",
    ]:
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_dir() and path.is_relative_to(ROOT)
        command.extend(["-v", f"{path.as_posix()}:/workspace/{relative}:ro"])
    command.extend(
        [
            "trueflag-assessment-verify:phase2-5",
            "python",
            "-B",
            "scripts/run_investigation_verification.py",
            "--inside",
        ]
    )
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT
    )
    process.stdin.write(
        json.dumps(
            {
                "database_url": url.render_as_string(hide_password=False),
                "full": full,
                "drafts": drafts,
            }
        )
    )
    process.stdin.close()
    counts = None
    for line in process.stdout:
        if line.startswith("INVESTIGATION_TEST_COUNTS:"):
            counts = json.loads(line.split(":", 1)[1])
        else:
            print(line, end="", flush=True)
    process.stdout.close()
    code = process.wait(timeout=60)
    if counts:
        filename = (
            (
                "runtime/phase3-5-2-full-tests.json"
                if full
                else "runtime/phase3-5-2-draft-tests.json"
            )
            if drafts
            else (
                "runtime/phase3-5-1-full-tests.json"
                if full
                else "runtime/phase3-5-1-investigation-tests.json"
            )
        )
        (ROOT / filename).write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(counts, sort_keys=True))
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--drafts", action="store_true")
    args = parser.parse_args()
    try:
        raise SystemExit(inside() if args.inside else main(args.full, args.drafts))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "investigation_verification_unavailable",
                    "live_database_migrated": False,
                }
            )
        )
        raise SystemExit(1) from None
