"""Run Claude ledger tests in disposable schemas on the existing recovery clone."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def inside():
    import pytest
    import rehearse_database_recovery as recovery

    state, control_url, control = recovery.inside_connection()
    control.dispose()
    url = control_url.set(database=state["database"])
    database_url = url.render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=database_url,
        TRUEFLAG_TEST_POSTGRES_URL=database_url,
        JWT_SECRET=secrets.token_urlsafe(48),
    )
    regression = "--regression" in sys.argv

    class CandidateRelease:
        @pytest.fixture(autouse=True)
        def candidate_release(self, monkeypatch):
            import app.core.release as release
            import app.core.release_metadata as metadata

            monkeypatch.setattr(release, "EXPECTED_SCHEMA_REVISION", "0020_claude_provider")
            monkeypatch.setattr(metadata, "EXPECTED_SCHEMA_REVISION", "0020_claude_provider")
            monkeypatch.setattr(release, "load_identity", lambda: metadata.unknown_identity())

    paths = ["backend/tests/test_claude_provider_postgres.py"]
    if regression:
        base = "backend/tests/test_investigation_drafts.py::"
        paths = [
            base + "test_simulated_pipeline_preserves_source_facts_case_and_provenance",
            base + "test_malicious_or_invalid_provider_output_is_withheld",
            base + "test_revocation_during_provider_execution_prevents_publication",
            base + "test_numeric_assertions_match_source_records_not_provider_claims",
        ]
    return pytest.main(
        [
            *paths,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            "/tmp/claude-provider-tests",
        ],
        plugins=[CandidateRelease()] if regression else [],
    )


def main():
    import rehearse_database_recovery as recovery
    from claude_migration_overlay import create_overlay

    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise RuntimeError("isolated_clone_required")
    command = recovery.linux_args(state, directory)[:-4]
    index = command.index("trueflag-assessment-verify:phase2-5")
    overlay = create_overlay()
    command[index:index] = ["-v", f"{overlay.as_posix()}:/workspace/backend/alembic/versions:ro"]
    command += ["python", "-B", "/workspace/scripts/run_claude_postgres_tests.py", "--inside"]
    if "--regression" in sys.argv:
        command.append("--regression")
    result = subprocess.run(
        command,
        input="",
        text=True,
        capture_output=True,
        timeout=180,
        cwd=ROOT,
    )
    # Avoid ever relaying the connection URL, key or provider inputs from exceptions.
    print(result.stdout, end="")
    if result.returncode and not result.stdout:
        print("PostgreSQL test process unavailable; details withheld.")
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(inside() if "--inside" in sys.argv else main())
    except Exception:
        print("PostgreSQL test process unavailable; no live database changes were attempted.")
        raise SystemExit(1) from None
