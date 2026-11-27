"""Run synthetic demo tests in disposable schemas on the isolated recovery clone."""

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
    return pytest.main(
        [
            "backend/tests/test_synthetic_demo_cases.py",
            "backend/tests/test_connected_scenario_catalog.py",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            "/tmp/synthetic-demo-tests",
        ]
    )


def main():
    import rehearse_database_recovery as recovery

    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise RuntimeError("isolated_clone_required")
    command = recovery.linux_args(state, directory)[:-4]
    command += ["python", "-B", "/workspace/scripts/run_synthetic_demo_tests.py", "--inside"]
    result = subprocess.run(
        command, input="", text=True, capture_output=True, timeout=240, cwd=ROOT
    )
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
