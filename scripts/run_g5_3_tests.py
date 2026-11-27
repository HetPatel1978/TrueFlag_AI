"""G5.3 acceptance in disposable schemas; candidate migrations never touch the demo."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = "--development" in sys.argv
REVISION = "0022_claude_development_scope" if DEVELOPMENT else "0021_regulatory_draft_bindings"


def inside():
    import pytest
    import rehearse_database_recovery as recovery

    state, url, control = recovery.inside_connection()
    control.dispose()
    db = url.set(database=state["database"]).render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=db, TRUEFLAG_TEST_POSTGRES_URL=db, JWT_SECRET=secrets.token_urlsafe(48)
    )

    class Candidate:
        @pytest.fixture(autouse=True)
        def release(self, monkeypatch):
            import app.core.release as release
            import app.core.release_metadata as metadata

            monkeypatch.setattr(release, "EXPECTED_SCHEMA_REVISION", REVISION)
            monkeypatch.setattr(metadata, "EXPECTED_SCHEMA_REVISION", REVISION)
            monkeypatch.setattr(release, "load_identity", lambda: metadata.unknown_identity())

    tests = [
        "backend/tests/test_durable_regulatory_drafts.py",
        "backend/tests/test_g5_3_claude_api.py",
    ]
    if "--regression" in sys.argv:
        tests = [
            "backend/tests/test_investigation_drafts.py",
            "backend/tests/test_draft_api.py",
            "backend/tests/test_human_casework.py",
            "backend/tests/test_regulatory_investigation.py",
            "backend/tests/test_regulatory_context.py",
        ]
    if "--security" in sys.argv:
        tests = [
            "backend/tests/test_snapshot_clock_integrity.py",
            "backend/tests/test_snapshot_clock_policy.py",
            "backend/tests/test_claude_contract.py",
            "backend/tests/test_claude_provider.py",
        ]
    if DEVELOPMENT:
        tests = ["backend/tests/test_claude_development_postgres.py"]
    return pytest.main(
        [*tests, "-q", "--tb=short", "-p", "no:cacheprovider", "--basetemp", "/tmp/g53-tests"],
        plugins=[Candidate()],
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
    overlay = create_overlay(regulatory=True, development=DEVELOPMENT)
    release_directory = overlay.with_name(overlay.name + "-release")
    release_directory.mkdir(exist_ok=False)
    (release_directory / "schema.py").write_text('EXPECTED_SCHEMA_REVISION = "' + REVISION + '"\n')
    identity = json.loads(
        (ROOT / "runtime/claude-demo-20261120/claude_candidate_release.json").read_text()
    )
    identity["expected_schema_revision"] = REVISION
    (release_directory / "release.json").write_text(json.dumps(identity))
    command[index:index] = [
        "-v",
        f"{overlay.as_posix()}:/workspace/backend/alembic/versions:ro",
        "-v",
        f"{(release_directory / 'schema.py').as_posix()}:/workspace/backend/app/core/schema.py:ro",
        "-v",
        f"{(release_directory / 'release.json').as_posix()}:/workspace/backend/app/_release.json:ro",
    ]
    command += ["python", "-B", "/workspace/scripts/run_g5_3_tests.py", "--inside"]
    for flag in ("--regression", "--security", "--development"):
        if flag in sys.argv:
            command.append(flag)
    result = subprocess.run(
        command, input="", text=True, capture_output=True, timeout=600, check=False, cwd=ROOT
    )
    print(result.stdout, end="")
    if result.returncode and not result.stdout:
        print("Candidate test process unavailable; details withheld.")
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(inside() if "--inside" in sys.argv else main())
    except Exception:
        print("Candidate test process unavailable; no live database changes attempted.")
        raise SystemExit(1) from None
