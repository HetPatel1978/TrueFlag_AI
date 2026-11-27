"""Run backend tests against the staged migration chain the native runtime deploys.

The repository's active migration head is 0019; candidates 0020-0023 live in
backend/alembic/candidates and are staged only into the native runtime's private source copy
(see windows_runtime.stage_source). Tests that need those tables (the model/migration drift
check, academic research) must run against that same staged chain.

  .venv-windows/Scripts/python.exe -B scripts/run_staged_tests.py backend/tests/<file>.py ...

Stages a fresh copy of the working tree under runtime/staged-tests/<id>/source, runs pytest
there against the native runtime's *test* database (never its application database), prints a
redacted summary and removes the copy. Linked assets are junctions and are only unlinked,
never followed, when the copy is removed.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
import windows_runtime  # noqa: E402

BASE = ROOT / "runtime/staged-tests"


def remove_staged(directory):
    """Unlink the junctions stage_source created (os.rmdir removes only the link), then delete
    the copy. Nothing behind a junction is ever traversed or deleted."""
    for link in (
        "source/assets/local/baseline",
        "source/assets/local/explanation_reference",
        "source/frontend/node_modules",
    ):
        target = directory / link
        if target.exists() or target.is_symlink():
            os.rmdir(target)  # junction: removes the link only
    shutil.rmtree(directory)


def main():
    tests = sys.argv[1:] or ["backend/tests"]
    _, state = windows_runtime.current()
    if state["test_url"] == state["database_url"]:
        raise SystemExit("refusing: test and application databases are the same")
    directory = BASE / uuid4().hex[:12]
    directory.mkdir(parents=True)
    try:
        source = windows_runtime.stage_source(directory, "source")
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
            }
        }
        env.update(
            PYTHONPATH=str(source / "backend"),
            DATABASE_URL=state["test_url"],
            TRUEFLAG_TEST_POSTGRES_URL=state["test_url"],
            JWT_SECRET="staged-test-" + "x" * 40,
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
        )
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                *tests,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            cwd=source,
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,
        )
        output = result.stdout + result.stderr
        for secret in (state["test_url"], state["database_url"]):
            output = output.replace(secret, "[redacted]")
        (BASE / "last-run.log").write_text(output, encoding="utf-8")
        print(output[-5000:])
        print(
            json.dumps({"staged_chain": "0019 + candidates 0020-0023", "exit": result.returncode})
        )
        return result.returncode
    finally:
        remove_staged(directory)


if __name__ == "__main__":
    raise SystemExit(main())
