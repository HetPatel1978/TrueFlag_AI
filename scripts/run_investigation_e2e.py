"""Strict-auth Chromium/real Linux PostgreSQL workbench fixture on the protected G2 clone."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def main():
    import rehearse_database_recovery as r
    from sqlalchemy.engine import URL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=[
            "investigation",
            "workbench",
            "batch",
            "design",
            "workflow",
            "all",
            "drafts",
            "human",
            "provider",
            "probe",
        ],
        default="investigation",
    )
    parser.add_argument("--grep", help="Optional focused Playwright test selection")
    options = parser.parse_args()
    if options.grep and len(options.grep) > 120:
        parser.error("Test selection exceeds supported bounds")

    root = (
        "g4-2b-1"
        if options.suite == "probe"
        else "g4-2b"
        if options.suite == "provider"
        else "g3-1"
        if options.suite == "human"
        else "g4-3a"
        if options.suite == "drafts"
        else "g2-3"
        if options.suite in {"workflow", "all"}
        else "g2-1"
    )
    marker = r.load(ROOT / f"runtime/{root}/current.json")
    directory = (ROOT / marker["directory"]).resolve(strict=True)
    r.check(
        directory.is_relative_to((ROOT / f"runtime/{root}").resolve()), "unsafe_browser_directory"
    )
    state = r.load(directory / "state.json")
    control = directory / ("browser-" + uuid4().hex)
    control.mkdir()
    network = "trueflag-g21-ui-" + uuid4().hex
    args = r.linux_args(state, directory)[:-4]
    image = args.pop()
    args += [
        "--name",
        "trueflag-g21-browser-" + state["test_run"][:12],
        "--network",
        network,
        "-p",
        "127.0.0.1:18010:8000",
        "-v",
        f"{control.as_posix()}:/test-control:rw",
        image,
        "python",
        "-B",
        "scripts/serve_frontend_acceptance.py",
    ]
    password = (directory / "isolated-password").read_text()
    url = URL.create(
        "postgresql+psycopg",
        username="rehearsal",
        password=password,
        host="db",
        port=5432,
        database=state["database"],
    )
    process = None
    try:
        # Docker's internal DB network does not forward published ports to Windows.
        # Only the disposable API joins this additional bridge; DB remains unexposed.
        r.run(
            ["docker", "network", "create", "--label", "trueflag.g21=" + state["test_run"], network]
        )
        process = subprocess.Popen(
            args,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        process.stdin.write(
            json.dumps(
                {
                    "database_url": url.render_as_string(hide_password=False),
                    "investigation_workbench": True,
                    "strict_auth": True,
                    "design_system": options.suite in {"design", "all"},
                    "case_workflows": options.suite in {"workflow", "all"},
                    "simulation_drafts": options.suite
                    in {"all", "drafts", "human", "provider", "probe"},
                    "expected_cluster": state["isolated_system_identifier"],
                    "forbidden_cluster": state["source"]["system_identifier"],
                    "expected_database": state["database"],
                }
            )
            + "\n"
        )
        process.stdin.flush()
        ready = json.loads(process.stdout.readline())
        r.check(ready.get("ready"), "browser_fixture_unavailable")
        fixture = control / "browser-fixture.json"
        r.save(fixture, ready)
        env = {
            **os.environ,
            "TRUEFLAG_E2E_FIXTURE": str(fixture),
            "TRUEFLAG_API_PROXY": "http://127.0.0.1:18010",
            "TRUEFLAG_DRAFT_SCREENSHOTS": str(control / "screenshots"),
            "TRUEFLAG_DESIGN_SCREENSHOTS": "../runtime/g2-3/screenshots/design-regression"
            if root == "g2-3"
            else "../runtime/g2-2/screenshots",
        }
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        result = subprocess.run(
            [
                npm,
                "run",
                "test:e2e",
                "--",
                *(
                    []
                    if options.suite == "all"
                    else [
                        ("drafts" if options.suite in {"provider", "probe"} else options.suite)
                        + ".spec.ts"
                    ]
                ),
                *(["--grep", options.grep] if options.grep else []),
            ],
            cwd=ROOT / "frontend",
            env=env,
            timeout=540,
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).replace(
            ready["password"], "[redacted fixture credential]"
        )
        (directory / "browser-results.txt").write_text(output, encoding="utf-8")
        (control / "browser-results.txt").write_text(output, encoding="utf-8")
        print(output)
        return result.returncode
    finally:
        if process:
            process.stdin.close()
            try:
                process.wait(timeout=55)
            except subprocess.TimeoutExpired:
                # Fixture containers own only ephemeral test schemas; never stop the database/demo.
                process.terminate()
                process.wait(timeout=10)
        inspected = r.run(["docker", "network", "inspect", network], accept_failure=True)
        if inspected.returncode == 0:
            details = json.loads(inspected.stdout)[0]
            r.check(
                details["Labels"].get("trueflag.g21") == state["test_run"], "ui_network_not_owned"
            )
            r.run(["docker", "network", "rm", network], accept_failure=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"browser_run": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
