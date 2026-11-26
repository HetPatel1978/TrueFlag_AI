"""Native isolated PostgreSQL acceptance. Reads protected runtime state; never .env/provider keys."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from windows_runtime import ROOT, clean_env, connection, current, stage_source


def utc_ns():
    # Python 3.11 uses the coarser GetSystemTimeAsFileTime. PostgreSQL's
    # sub-millisecond comparison needs the documented precise Windows UTC API.
    import ctypes
    from ctypes import wintypes

    value = wintypes.FILETIME()
    api = ctypes.WinDLL("kernel32").GetSystemTimePreciseAsFileTime
    api.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
    api(ctypes.byref(value))
    return ((value.dwHighDateTime << 32) | value.dwLowDateTime) * 100 - 11644473600000000000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", choices=["clock", "backend", "ml", "parity"])
    parser.add_argument(
        "--tests", nargs="+", help="Explicit backend test filenames within the isolated source copy"
    )
    parser.add_argument(
        "--candidate-source",
        action="store_true",
        help="Test a fresh private source copy without changing the running app",
    )
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("native_windows_required")
    directory, state = current()
    with connection(state):
        pass
    output = directory / (args.scope + "-verification-" + uuid4().hex)
    output.mkdir()
    if args.candidate_source:
        if args.scope != "backend":
            raise RuntimeError("candidate_backend_only")
        state = dict(state, source=str(stage_source(output, "source")))
    env = clean_env(state)
    if args.scope == "clock":
        os.environ.update(env)
        sys.path.insert(0, env["PYTHONPATH"])
        from app.core.database import make_engine
        from app.services.snapshot_clock import SnapshotTime

        engine = make_engine(state["database_url"])
        clock = SnapshotTime(engine)
        observations = []
        with connection(state) as c:
            for _ in range(300):
                start = utc_ns()
                value = c.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
                end = utc_ns()
                observation = clock.observe()
                observations.append(
                    (
                        start,
                        end,
                        int(value * 1_000_000_000),
                        time.perf_counter_ns(),
                        observation.epoch,
                    )
                )
                time.sleep(0.2)
        result = {
            "observations": observations,
            "samples": len(observations),
            "host_backsteps": sum(b[0] < a[0] for a, b in zip(observations, observations[1:])),
            "postgres_backsteps": sum(b[2] < a[2] for a, b in zip(observations, observations[1:])),
            "outside_host_roundtrip": sum(not a <= c <= b for a, b, c, _, _ in observations),
            "epoch_changes": sum(b[4] != a[4] for a, b in zip(observations, observations[1:])),
            "provider_requests": 0,
        }
        (output / "clock.json").write_text(json.dumps(result, indent=2))
        engine.dispose()
        summary = {k: v for k, v in result.items() if k != "observations"}
        print(json.dumps(summary))
        return int(
            any(
                summary[k]
                for k in (
                    "host_backsteps",
                    "postgres_backsteps",
                    "outside_host_roundtrip",
                    "epoch_changes",
                )
            )
        )
    if args.scope == "parity":
        os.environ.update(env)
        sys.path.insert(0, env["PYTHONPATH"])
        from dataclasses import asdict

        from trueflag_ml.explanation_regression import run_explanation_regression
        from trueflag_ml.policy_regression import run_policy_regression
        from trueflag_ml.regression import run_regression

        score, policy = run_regression(), run_policy_regression()
        explanation = run_explanation_regression()
        result = {
            "scores": asdict(score),
            "policies": asdict(policy),
            "explanations": asdict(explanation),
            "passed": score.passed and policy.passed and explanation.passed,
            "provider_requests": 0,
        }
        (output / "parity.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return int(not result["passed"])
    env["TRUEFLAG_TEST_POSTGRES_URL"] = state["test_url"]
    env["TRUEFLAG_REQUIRE_SHAP"] = "1"
    env["TRUEFLAG_TEST_REAL_ASSESSMENT"] = "1"
    source = Path(state["source"])
    # Copy the reviewed test updates, not application code or migration history.
    shutil.copytree(
        ROOT / "backend/tests",
        source / "backend/tests",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    paths = (
        [str(source / "backend/tests")]
        if args.scope == "backend"
        else [str(source / "backend/ml_tests")]
    )
    if args.tests:
        if args.scope != "backend" or any(
            Path(name).name != name or not name.startswith("test_") or not name.endswith(".py")
            for name in args.tests
        ):
            raise RuntimeError("bounded_backend_test_selection_required")
        paths = [str(source / "backend/tests" / name) for name in args.tests]
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            *paths,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "--junitxml=" + str(output / "junit.xml"),
        ],
        cwd=source,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    raw = result.stdout + result.stderr
    from sqlalchemy.engine import make_url

    for value in (state["test_url"], state["database_url"], make_url(state["test_url"]).password):
        raw = raw.replace(value, "[credential redacted]")
    (output / "pytest.txt").write_text(raw)
    print(raw[-14000:])
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
