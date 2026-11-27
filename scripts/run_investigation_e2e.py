"""Strict-auth Chromium/real Linux PostgreSQL workbench fixture on the protected G2 clone.

Each spec file gets its own disposable fixture (fresh schema, fresh API listener), so one
spec's duration or failure cannot take the fixture down for the specs after it. Before a spec
starts, the fixture's /health endpoint must answer; otherwise that spec fails fast with
"fixture not reachable on :18010" instead of 60 s locator timeouts or Vite proxy 500s.

The fixture lifetime defaults to 600 s per spec and can be raised for a long spec with
TRUEFLAG_E2E_FIXTURE_LIFETIME_SECONDS (60-3600). Playwright is stopped 30 s before the
fixture would expire, so a spec that runs too long is reported as such.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

FIXTURE_PORT = 18010
FIXTURE_URL = f"http://127.0.0.1:{FIXTURE_PORT}"
LIFETIME_ENV = "TRUEFLAG_E2E_FIXTURE_LIFETIME_SECONDS"
DEFAULT_LIFETIME, MIN_LIFETIME, MAX_LIFETIME = 600, 60, 3600
PLAYWRIGHT_MARGIN = 30
SUMMARY = re.compile(r"^\s+(\d+) (passed|failed|skipped|flaky|did not run|interrupted)\b")


def fixture_lifetime(environ=os.environ):
    raw = environ.get(LIFETIME_ENV, "").strip()
    if not raw:
        return DEFAULT_LIFETIME
    if not raw.isdigit() or not MIN_LIFETIME <= int(raw) <= MAX_LIFETIME:
        raise ValueError(f"{LIFETIME_ENV} must be an integer from {MIN_LIFETIME} to {MAX_LIFETIME}")
    return int(raw)


def spec_files(suite):
    if suite == "all":
        return sorted(p.name for p in (ROOT / "frontend/e2e").glob("*.spec.ts"))
    return [("drafts" if suite in {"provider", "probe"} else suite) + ".spec.ts"]


def fixture_healthy(attempts=10, delay=0.5, url=FIXTURE_URL + "/health"):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200 and json.loads(response.read()).get("status") == "ok":
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(delay)
    return False


def summarize(output):
    counts = {}
    for line in output.splitlines():
        match = SUMMARY.match(line)
        if match:
            counts[match.group(2)] = counts.get(match.group(2), 0) + int(match.group(1))
    return counts


def kill_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGKILL)


def stream(command, *, cwd, env, timeout, redact, sink):
    """Run Playwright with output streamed line by line (no pipe left to hang on exit)."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **({} if os.name == "nt" else {"start_new_session": True}),
    )
    collected = []

    def pump():
        for line in process.stdout:
            line = line.replace(redact, "[redacted fixture credential]")
            collected.append(line)
            sink(line)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        code = 124
        message = (
            f"\n[e2e] spec exceeded {timeout} s (fixture lifetime minus {PLAYWRIGHT_MARGIN} s); "
            f"stopped. Raise {LIFETIME_ENV} for this spec.\n"
        )
        collected.append(message)
        sink(message)
    reader.join(timeout=30)
    return code, "".join(collected)


def wait_container_gone(r, name, timeout=60):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if r.run(["docker", "inspect", name], accept_failure=True).returncode != 0:
            return True
        time.sleep(1)
    return False


def run_spec(r, URL, options, root, directory, state, spec, lifetime, sink):
    control = directory / ("browser-" + uuid4().hex)
    control.mkdir()
    network = "trueflag-g21-ui-" + uuid4().hex
    name = "trueflag-g21-browser-" + state["test_run"][:12]
    r.check(wait_container_gone(r, name), "previous_fixture_still_present")
    args = r.linux_args(state, directory)[:-4]
    image = args.pop()
    args += [
        "--name",
        name,
        "--network",
        network,
        "-p",
        f"127.0.0.1:{FIXTURE_PORT}:8000",
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
                    "lifetime_seconds": lifetime,
                }
            )
            + "\n"
        )
        process.stdin.flush()
        ready = json.loads(process.stdout.readline() or "{}")
        r.check(ready.get("ready"), "browser_fixture_unavailable")
        if not fixture_healthy():
            message = f"[e2e] {spec}: fixture not reachable on :{FIXTURE_PORT}; spec not run\n"
            sink(message)
            return 1, message
        fixture = control / "browser-fixture.json"
        r.save(fixture, ready)
        env = {
            **os.environ,
            "TRUEFLAG_E2E_FIXTURE": str(fixture),
            "TRUEFLAG_API_PROXY": FIXTURE_URL,
            "TRUEFLAG_DRAFT_SCREENSHOTS": str(control / "screenshots"),
            "TRUEFLAG_DESIGN_SCREENSHOTS": "../runtime/g2-3/screenshots/design-regression"
            if root == "g2-3"
            else "../runtime/g2-2/screenshots",
        }
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        code, output = stream(
            [
                npm,
                "run",
                "test:e2e",
                "--",
                spec,
                # Per-spec output folder: each Playwright run clears its own outputDir.
                "--output",
                f"../runtime/playwright-results/{spec.removesuffix('.spec.ts')}",
                *(["--grep", options.grep] if options.grep else []),
            ],
            cwd=ROOT / "frontend",
            env=env,
            timeout=lifetime - PLAYWRIGHT_MARGIN,
            redact=ready["password"],
            sink=sink,
        )
        (control / "browser-results.txt").write_text(output, encoding="utf-8")
        return code, output
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
    parser.add_argument(
        "--spec", action="append", help="With --suite all: run only this spec file (repeatable)"
    )
    options = parser.parse_args()
    specs = spec_files(options.suite)
    if options.spec:
        if options.suite != "all" or not set(options.spec) <= set(specs):
            parser.error("--spec needs --suite all and names from frontend/e2e/*.spec.ts")
        specs = [s for s in specs if s in options.spec]
    if options.grep and len(options.grep) > 120:
        parser.error("Test selection exceeds supported bounds")
    try:
        lifetime = fixture_lifetime()
    except ValueError as error:
        parser.error(str(error))

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

    # Playwright prints non-ASCII marks; a redirected Windows console would otherwise be cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    def sink(line):
        print(line, end="", flush=True)

    results, outputs = [], []
    for spec in specs:
        sink(f"\n[e2e] {spec}: starting a fresh fixture (lifetime {lifetime} s)\n")
        started = time.monotonic()
        try:
            code, output = run_spec(r, URL, options, root, directory, state, spec, lifetime, sink)
        except Exception as error:
            # A fixture that cannot start fails only this spec; the next spec gets a new one.
            code, output = 1, f"[e2e] {spec}: fixture failed ({type(error).__name__})\n"
            sink(output)
        counts = summarize(output)
        results.append((spec, code, counts, time.monotonic() - started))
        outputs.append(f"===== {spec} (exit {code})\n{output}")
    (directory / "browser-results.txt").write_text("\n".join(outputs), encoding="utf-8")

    totals = {}
    sink("\n[e2e] summary\n")
    for spec, code, counts, seconds in results:
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        detail = ", ".join(f"{v} {k}" for k, v in counts.items()) or "no Playwright summary"
        sink(f"  {spec:<26} exit {code:<4} {detail} ({seconds:.0f} s)\n")
    sink("  total: " + (", ".join(f"{v} {k}" for k, v in totals.items()) or "none") + "\n")
    return 0 if all(code == 0 for _, code, _, _ in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"browser_run": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
