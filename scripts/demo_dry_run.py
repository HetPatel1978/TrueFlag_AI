"""Isolated dry run of the native Windows stack for the demo case set.

  up     create a fresh database on the native runtime's PostgreSQL cluster, migrate it,
         bootstrap users and workers, and start API, workers and the Vite frontend from the
         working tree on new ports (state in runtime/demo-dry-run/<id>/)
  down   stop those processes and DROP the dry-run database
  restart  restart the processes (new code) and keep the database
  child  internal: run one runtime role against the dry-run state

The native application database, its users and its stored records are never opened for
writing. The dry run copies the native runtime configuration (research on, simulation off,
provider calls off), including the owner's research scope file, which does not cover dry-run
cases, so per-case AI research stays scope-denied exactly as it would for new cases.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
import windows_runtime as runtime  # noqa: E402

BASE = ROOT / "runtime/demo-dry-run"
USERS = (
    ("windowsadmin", "admin"),
    ("windowsanalyst", "analyst"),
    ("windowssupervisor", "supervisor"),
)


def current():
    marker = BASE / "current.json"
    directory = Path(json.loads(marker.read_text())["directory"]).resolve(strict=True)
    if not directory.is_relative_to(BASE.resolve()):
        raise RuntimeError("dry_run_directory_required")
    return directory, json.loads((directory / "state.json").read_text())


def admin_connection(native):
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(native["database_url"])
    return psycopg.connect(
        host="127.0.0.1",
        port=url.port,
        dbname="postgres",
        user=url.username,
        password=url.password,
        autocommit=True,
    )


def up():
    from psycopg import sql
    from sqlalchemy.engine import make_url

    if (BASE / "current.json").exists():
        raise SystemExit("a dry run is already up; run 'down' first")
    _, native = runtime.current()
    tag = uuid4().hex[:12]
    directory = BASE / tag
    for sub in ("staging", "numba"):
        (directory / sub).mkdir(parents=True)
    database = f"tf_windows_test_demo_{tag}"
    url = make_url(native["database_url"]).set(database=database)
    ports = [runtime_port() for _ in range(2)]
    state = {
        **native,
        "directory": str(directory),
        "source": str(ROOT),
        "database_url": url.render_as_string(hide_password=False),
        "test_url": url.render_as_string(hide_password=False),
        "api_port": ports[0],
        "frontend_port": ports[1],
        "jwt_secret": secrets.token_urlsafe(48),
        "worker_token": secrets.token_hex(32),
        "import_token": secrets.token_hex(32),
        "evidence_token": secrets.token_hex(32),
        "dry_run_database": database,
        # The cluster's data directory stays the native runtime's (checked on every connect).
        "native_directory": native["directory"],
    }
    with admin_connection(native) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    (directory / "state.json").write_text(json.dumps(state, indent=2))
    (BASE / "current.json").write_text(json.dumps({"directory": str(directory)}))
    env = runtime.clean_env(state)
    migrated = subprocess.run(
        [
            str(runtime.PYTHON),
            "-m",
            "alembic",
            "-c",
            str(ROOT / "backend/alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=300,
    )
    (directory / "migration.log").write_bytes(migrated.stdout + migrated.stderr)
    if migrated.returncode:
        raise SystemExit("migration failed; see migration.log")
    os.environ.update(env)
    sys.path.insert(0, env["PYTHONPATH"])
    from app.core.database import make_engine
    from app.models import AuditEvent, User
    from app.security.auth import password_hash
    from sqlalchemy.orm import Session

    engine = make_engine(state["database_url"])
    logins = {}
    with Session(engine) as session, session.begin():
        for username, role in USERS:
            secret = secrets.token_urlsafe(24)
            user = User(username=username, role=role, password_hash=password_hash.hash(secret))
            session.add(user)
            session.flush()
            session.add(
                AuditEvent(actor_id=user.id, action="user.bootstrap", resource_id=str(user.id))
            )
            logins[username] = {"password": secret, "role": role}
    engine.dispose()
    (directory / "login.json").write_text(json.dumps(logins, indent=2))
    runtime.setup_workers(state)
    start_processes(directory, state)
    print(
        json.dumps(
            {
                "status": "up",
                "api_port": state["api_port"],
                "frontend_port": state["frontend_port"],
                "database": database,
                "directory": str(directory),
            }
        )
    )


def start_processes(directory, state):
    env = runtime.clean_env(state)
    if state.get("simulation"):
        # Dry run only: offline simulated findings (labelled in the UI; no provider call).
        env["INVESTIGATION_SIMULATION_ENABLED"] = "true"
    processes = {}
    for role in ("api", "assessment", "import", "evidence", "frontend"):
        log = (directory / f"{role}.log").open("ab")
        if role == "frontend":
            command = [
                shutil.which("node.exe"),
                str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(state["frontend_port"]),
                "--strictPort",
            ]
            cwd, process_env = str(ROOT / "frontend"), {**env}
        else:
            command = [
                str(runtime.PYTHON),
                "-B",
                str(Path(__file__).resolve()),
                "child",
                "--role",
                role,
            ]
            cwd, process_env = str(ROOT), env
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=process_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        processes[role] = process.pid
    (directory / "pids.json").write_text(json.dumps(processes))


def stop_processes(directory):
    (directory / "stop").write_text("stop")
    time.sleep(6)
    for pid in json.loads((directory / "pids.json").read_text()).values():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    (directory / "stop").unlink()


def restart(simulation=None):
    directory, state = current()
    if simulation is not None:
        state["simulation"] = simulation
        (directory / "state.json").write_text(json.dumps(state, indent=2))
    stop_processes(directory)
    start_processes(directory, state)
    print(
        json.dumps(
            {
                "status": "restarted",
                "api_port": state["api_port"],
                "frontend_port": state["frontend_port"],
            }
        )
    )


def runtime_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def down():
    from psycopg import sql

    directory, state = current()
    stop_processes(directory)
    _, native = runtime.current()
    database = state["dry_run_database"]
    if not database.startswith("tf_windows_test_demo_"):
        raise SystemExit("refusing to drop a non dry-run database")
    with admin_connection(native) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (database,)
        )
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
        remaining = connection.execute(
            "SELECT count(*) FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()[0]
    (BASE / "current.json").unlink()
    print(json.dumps({"status": "down", "dropped": database, "remaining": remaining}))


def child(role):
    original = runtime.connection

    def connection(state, *, test=False):
        return original({**state, "directory": state["native_directory"]}, test=test)

    runtime.current = current
    runtime.connection = connection
    _, state = current()
    if state.get("simulation"):
        clean_env = runtime.clean_env
        runtime.clean_env = lambda s: {**clean_env(s), "INVESTIGATION_SIMULATION_ENABLED": "true"}
    if role == "evidence" and state.get("simulation"):
        return simulation_evidence_child(state)
    runtime.child(role)


def simulation_evidence_child(state):
    """Evidence role plus the offline simulated-findings worker (dry run only; no provider)."""
    import threading

    directory, _ = current()
    env = runtime.clean_env(state)
    os.environ.clear()
    os.environ.update({**env, "INVESTIGATION_SIMULATION_ENABLED": "true"})
    sys.path.insert(0, env["PYTHONPATH"])
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.core.release import require_compatible
    from app.services.investigation_coordinator import InvestigationCoordinator
    from app.services.investigation_drafts import InvestigationDraftService
    from app.services.research_drafts import ResearchDraftService

    engine = make_engine(state["database_url"])
    require_compatible(engine)
    settings = Settings(_env_file=None)
    stop = threading.Event()
    token = state["evidence_token"]
    try:
        while not stop.is_set() and not (directory / "stop").exists():
            if InvestigationCoordinator(engine, settings).run_once(token) is None:
                if InvestigationDraftService(engine, settings).run_once(token) is None:
                    ResearchDraftService(engine, settings).run_requested_once(token)
            stop.wait(2)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["up", "down", "restart", "child"])
    parser.add_argument("--role")
    parser.add_argument(
        "--simulation", action="store_true", help="restart with offline simulated findings on"
    )
    options = parser.parse_args()
    if options.command == "up":
        up()
    elif options.command == "down":
        down()
    elif options.command == "restart":
        restart(True if options.simulation else None)
    else:
        child(options.role)


if __name__ == "__main__":
    main()
