"""Pinned Linux/PG gate tests on the recovery CLONE; no source approval/publication."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


class GateReport:
    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.passed:
            for _, captured in report.sections:
                for line in captured.splitlines():
                    if line.startswith("REGULATORY_CANDIDATE_REPORT:"):
                        print("\n" + line)

    def pytest_terminal_summary(self, terminalreporter):
        stats = terminalreporter.stats
        print(
            "\nREGULATORY_GATE_TEST_COUNTS:"
            + json.dumps(
                {
                    "passed": len(stats.get("passed", [])),
                    "failed": len(stats.get("failed", [])) + len(stats.get("error", [])),
                    "skipped": len(stats.get("skipped", [])),
                }
            )
        )


def inside():
    import secrets

    import pytest
    from sqlalchemy.engine import make_url

    payload = json.loads(sys.stdin.read(65537))
    url = make_url(payload["database_url"])
    if url.host != "db" or not url.database.startswith("tf_reference_gate_clone_"):
        raise RuntimeError("isolated_clone_required")
    os.environ["DATABASE_URL"] = payload["database_url"]
    os.environ["TRUEFLAG_TEST_POSTGRES_URL"] = payload["database_url"]
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    return pytest.main(
        [
            "backend/tests/test_reference_parser.py",
            "backend/tests/test_references.py",
            "backend/tests/test_regulatory_approval_gate.py",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            "/tmp/regulatory-gate",
        ],
        plugins=[GateReport()],
    )


def host():
    from app.core.config import Settings
    from sqlalchemy.engine import make_url

    migration = json.loads((ROOT / "runtime/phase3-4-approval-migration.json").read_bytes())
    assert migration["status"] == "PASS" and migration["restore_verified"]
    private = (ROOT / migration["private_recovery_directory"]).resolve(strict=True)
    assert private.is_relative_to((ROOT / "runtime").resolve())
    manifest = json.loads((private / "recovery-manifest.json").read_bytes())
    database = manifest["clone_database"]
    assert database.startswith("tf_reference_gate_clone_") and len(database) == 56
    url = make_url(Settings().database_url)
    assert url.host in {"127.0.0.1", "localhost"} and database != url.database
    url = url.set(database=database, host="db", port=5432)
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
    for relative in ["backend", "scripts", "contracts", "assets/local/regulatory/proposed"]:
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_relative_to(ROOT) and path.is_dir()
        command.extend(["-v", f"{path.as_posix()}:/workspace/{relative}:ro"])
    command.extend(
        [
            "trueflag-assessment-verify:phase2-5",
            "python",
            "-B",
            "scripts/run_regulatory_approval_gate.py",
            "--inside",
        ]
    )
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT
    )
    process.stdin.write(json.dumps({"database_url": url.render_as_string(hide_password=False)}))
    process.stdin.close()
    report = counts = None
    for line in process.stdout:
        if line.startswith("REGULATORY_CANDIDATE_REPORT:"):
            report = json.loads(line.split(":", 1)[1])
        elif line.startswith("REGULATORY_GATE_TEST_COUNTS:"):
            counts = json.loads(line.split(":", 1)[1])
        else:
            print(line, end="", flush=True)
    process.stdout.close()
    code = process.wait(timeout=60)
    if code:
        return code
    assert report and counts and counts["failed"] == counts["skipped"] == 0
    assert (
        report["independent_labels"]
        == report["approved_sources"]
        == report["published_releases"]
        == 0
    )
    report["test_counts"] = counts
    (ROOT / "runtime/phase3-4-approval-candidate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {k: v for k, v in report.items() if k != "observations"}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(inside() if "--inside" in sys.argv else host())
    except Exception:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "regulatory_gate_verification_unavailable",
                    "source_publication_attempted": False,
                }
            )
        )
        raise SystemExit(1) from None
