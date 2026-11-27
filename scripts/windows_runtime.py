"""Owned, isolated native Windows development runtime; never reads .env or enables paid AI."""

import argparse
import csv
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime/windows-native"
MARKER = BASE / "current.json"
PYTHON = ROOT / ".venv-windows/Scripts/python.exe"
REVISION = "0023_durable_regulatory_start"


def private_directory(path):
    path.mkdir(parents=True, exist_ok=False)
    # Actual token SID, not an asserted username; protect only this new workspace directory.
    row = next(
        csv.reader(
            [subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip()]
        )
    )
    sid = row[-1]
    if not sid.startswith("S-1-"):
        raise RuntimeError("owner_identity_unavailable")
    subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
        ],
        check=True,
        capture_output=True,
    )


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)


def current():
    directory = Path(json.loads(MARKER.read_text())["directory"]).resolve(strict=True)
    if not directory.is_relative_to(BASE.resolve()) or directory == BASE.resolve():
        raise RuntimeError("owned_runtime_required")
    state = json.loads((directory / "state.json").read_text())
    return directory, state


def process_identity(pid):
    """Kernel creation identity prevents adopting a reused PID during recovery."""
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() in (87, 1168):
            return None
        raise RuntimeError("process_identity_unavailable")
    try:
        exit_code = wintypes.DWORD()
        if not api.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise RuntimeError("process_identity_unavailable")
        if exit_code.value != 259:
            return None
        values = [wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle, *[ctypes.byref(value) for value in values]):
            raise RuntimeError("process_identity_unavailable")
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
    finally:
        api.CloseHandle(handle)


def discard_stale_supervisor(directory):
    marker = directory / "supervisor.json"
    if marker.exists():
        record = json.loads(marker.read_text())
        actual = process_identity(record["pid"])
        if actual is None or record.get("creation") is not None and actual != record["creation"]:
            marker.unlink()


def clean_env(state):
    values = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    }
    values.update(
        PYTHONPATH=str(Path(state["source"]) / "backend"),
        DATABASE_URL=state["database_url"],
        JWT_SECRET=state["jwt_secret"],
        APP_ENV="local",
        CORS_ORIGINS=json.dumps(
            [f"http://127.0.0.1:{state['frontend_port']}", f"http://127.0.0.1:{state['api_port']}"]
        ),
        CSV_STAGING_ROOT=str(Path(state["directory"]) / "staging"),
        BATCH_ASSESSMENT_DISPATCH_ENABLED="true",
        ACCESS_TOKEN_MINUTES="60",
        INVESTIGATION_SIMULATION_ENABLED="false",
        INVESTIGATION_EXTERNAL_ENABLED="false",
        ANTHROPIC_SYNTHETIC_DEMO_ENABLED="false",
        ANTHROPIC_ANALYST_GENERATION_ENABLED="false",
        REGULATORY_INVESTIGATION_ENABLED="false",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMBA_CACHE_DIR=str(Path(state["directory"]) / "numba"),
        TRUEFLAG_API_PROXY=f"http://127.0.0.1:{state['api_port']}",
    )
    if state.get("research"):
        values.update(
            ACADEMIC_RESEARCH_ENABLED="true",
            ACADEMIC_RESEARCH_SCOPE_FILE=state["research"]["scope_file"],
            ACADEMIC_RESEARCH_SCOPE_SHA256=state["research"]["scope_sha256"],
            ACADEMIC_RESEARCH_APPROVAL_FILE=state["research"]["approval_file"],
            ACADEMIC_RESEARCH_CREDENTIAL_FILE=str(ROOT / ".env"),
            ANTHROPIC_SYNTHETIC_DEMO_ENABLED="true",
        )
        if state["research"].get("approver_file"):
            values["ACADEMIC_RESEARCH_APPROVER_FILE"] = state["research"]["approver_file"]
    return values


def pg(state, *arguments):
    # Detached postgres descendants retain inherited handles on Windows. A PIPE
    # makes communicate() wait for server EOF even after pg_ctl has exited.
    with (Path(state["directory"]) / "pg-ctl.log").open("ab") as log:
        return subprocess.run(
            [str(Path(state["pg_bin"]) / "pg_ctl.exe"), *arguments],
            stdout=log,
            stderr=log,
            timeout=60,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


def pg_start(directory, state):
    if pg(state, "status", "-D", str(directory / "data")).returncode:
        result = pg(
            state,
            "start",
            "-w",
            "-D",
            str(directory / "data"),
            "-l",
            str(directory / "postgres.log"),
        )
        if result.returncode:
            raise RuntimeError("native_postgresql_start_failed")


def connection(state, *, test=False):
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(state["test_url"] if test else state["database_url"])
    if (
        url.host != "127.0.0.1"
        or url.port != state["pg_port"]
        or not url.database.startswith("tf_windows_")
    ):
        raise RuntimeError("isolated_database_required")
    config = dict(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    )
    c = psycopg.connect(**config)
    with c.cursor() as cursor:
        cursor.execute("SELECT system_identifier::text FROM pg_control_system()")
        if cursor.fetchone()[0] != state["cluster_id"]:
            c.close()
            raise RuntimeError("cluster_identity_mismatch")
        cursor.execute("SHOW data_directory")
        if Path(cursor.fetchone()[0]).resolve() != Path(state["directory"]).resolve() / "data":
            c.close()
            raise RuntimeError("data_directory_mismatch")
    return c


def stage_source(directory, name):
    from prepare_native_demo import copy_public

    source = directory / name
    copy_public(ROOT, source)
    if (ROOT / "assets/local/regulatory/proposed").is_dir():
        shutil.copytree(
            ROOT / "assets/local/regulatory/proposed", source / "assets/local/regulatory/proposed"
        )
    for name in (
        "0020_claude_provider",
        "0021_regulatory_draft_bindings",
        "0022_claude_development_scope",
        "0023_durable_regulatory_start",
    ):
        shutil.copyfile(
            source / f"backend/alembic/candidates/{name}.py",
            source / f"backend/alembic/versions/{name}.py",
        )
    (source / "backend/app/core/schema.py").write_text(f'EXPECTED_SCHEMA_REVISION = "{REVISION}"\n')
    # Junctions provide existing trusted assets/dependencies without copying or changing them.
    for target, origin in (
        (source / "assets/local/baseline", ROOT / "assets/local/baseline"),
        (
            source / "assets/local/explanation_reference",
            ROOT / "assets/local/explanation_reference",
        ),
        (source / "frontend/node_modules", ROOT / "frontend/node_modules"),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        if not origin.is_dir():
            raise RuntimeError("existing_assets_or_frontend_dependencies_missing")
        command = "$spec = [Console]::In.ReadToEnd() | ConvertFrom-Json; $null = New-Item -ItemType Junction -Path $spec.target -Target $spec.origin -ErrorAction Stop"
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            input=json.dumps({"target": str(target), "origin": str(origin)}).encode(),
            check=True,
            capture_output=True,
        )
    subprocess.run(
        [str(PYTHON), str(source / "scripts/build_release_manifest.py")],
        cwd=source,
        capture_output=True,
        check=True,
    )
    return source


def initialize(pg_bin):

    if os.name != "nt" or sys.version_info[:2] != (3, 11) or MARKER.exists():
        raise RuntimeError("new_windows_runtime_required")
    for executable in ("postgres.exe", "pg_ctl.exe", "initdb.exe"):
        if not (pg_bin / executable).is_file():
            raise RuntimeError("native_postgresql_binaries_required")
    if not BASE.exists():
        private_directory(BASE)
    directory = BASE / uuid4().hex
    private_directory(directory)
    source = stage_source(directory, "source")
    for name in ("staging", "numba"):
        (directory / name).mkdir()

    def unused_port():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    port, api_port, frontend_port = unused_port(), unused_port(), unused_port()
    password, user, tag = secrets.token_hex(32), "tf_windows", uuid4().hex[:12]
    password_file = directory / "postgres-password"
    password_file.write_text(password)
    result = subprocess.run(
        [
            str(pg_bin / "initdb.exe"),
            "-D",
            str(directory / "data"),
            "-U",
            user,
            "--pwfile",
            str(password_file),
            "--auth-host=scram-sha-256",
            "--auth-local=scram-sha-256",
            "--encoding=UTF8",
            "--locale=C",
        ],
        capture_output=True,
        timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    (directory / "initdb.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("native_initdb_failed")
    with (directory / "data/postgresql.conf").open("a") as stream:
        stream.write(
            f"\nlisten_addresses='127.0.0.1'\nport={port}\ntimezone='UTC'\nlog_statement='none'\nlog_min_error_statement='panic'\n"
        )
    state = dict(
        directory=str(directory),
        source=str(source),
        pg_bin=str(pg_bin),
        pg_port=port,
        api_port=api_port,
        frontend_port=frontend_port,
        cluster_id=None,
        jwt_secret=secrets.token_urlsafe(48),
        worker_token=secrets.token_hex(32),
        import_token=secrets.token_hex(32),
        evidence_token=secrets.token_hex(32),
        database_url=f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/tf_windows_app_{tag}",
        test_url=f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/tf_windows_test_{tag}",
    )
    pg_start(directory, state)
    import psycopg
    from psycopg import sql

    with psycopg.connect(
        host="127.0.0.1",
        port=port,
        dbname="postgres",
        user=user,
        password=password,
        autocommit=True,
    ) as c:
        state["cluster_id"] = c.execute(
            "SELECT system_identifier::text FROM pg_control_system()"
        ).fetchone()[0]
        for name in (f"tf_windows_app_{tag}", f"tf_windows_test_{tag}"):
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    write(directory / "state.json", state)
    env = clean_env(state)
    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "alembic",
            "-c",
            str(source / "backend/alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=source,
        env=env,
        capture_output=True,
        timeout=90,
    )
    (directory / "migration.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("native_migration_failed")
    write(MARKER, {"directory": str(directory)})
    # Explicit supported bootstrap over existing schema; never import old demo users/data.
    os.environ.update(env)
    sys.path.insert(0, env["PYTHONPATH"])
    from app.core.database import make_engine
    from app.models import AuditEvent, User
    from app.security.auth import password_hash
    from sqlalchemy.orm import Session

    engine = make_engine(state["database_url"])
    logins = {}
    with Session(engine) as session, session.begin():
        for username, role in (
            ("windowsadmin", "admin"),
            ("windowsanalyst", "analyst"),
            ("windowssupervisor", "supervisor"),
        ):
            secret = secrets.token_urlsafe(24)
            user_record = User(
                username=username, role=role, password_hash=password_hash.hash(secret)
            )
            session.add(user_record)
            session.flush()
            session.add(
                AuditEvent(
                    actor_id=user_record.id,
                    action="user.bootstrap",
                    resource_id=str(user_record.id),
                )
            )
            logins[username] = {"password": secret, "role": role}
    write(directory / "login.json", logins)
    engine.dispose()
    print(json.dumps({"status": "initialized", "schema": REVISION, "provider_requests": 0}))


def child(role):
    directory, state = current()
    env = clean_env(state)
    os.environ.clear()
    os.environ.update(env)
    sys.path.insert(0, env["PYTHONPATH"])
    with connection(state):
        pass
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.core.release import require_compatible

    engine = make_engine(state["database_url"])
    require_compatible(engine)
    stop = threading.Event()

    def watch():
        while not stop.wait(0.2):
            if (directory / "stop").exists():
                stop.set()

    threading.Thread(target=watch, daemon=True).start()
    if role == "api":
        import uvicorn
        from app.main import create_app

        application = create_app(Settings(_env_file=None), engine)
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=state["api_port"],
                access_log=False,
                log_level="warning",
            )
        )

        def shutdown():
            stop.wait()
            server.should_exit = True

        threading.Thread(target=shutdown, daemon=True).start()
        server.run()
        return
    settings = Settings(_env_file=None)
    if role == "assessment":
        from app.core.release import verify_worker_artifacts
        from app.services.assessment_jobs import AssessmentJobService
        from app.workers.assessment_worker import AssessmentWorker

        verify_worker_artifacts()
        queue = AssessmentJobService(engine)
        worker = AssessmentWorker(queue, state["worker_token"], stop)
        step = worker.run_once
    elif role == "import":
        from app.services.csv_imports import CSVImportService
        from app.workers.csv_import_worker import CSVImportWorker

        step = CSVImportWorker(CSVImportService(engine, settings), state["import_token"]).run_once
    elif role == "evidence":
        from app.services.investigation_coordinator import InvestigationCoordinator
        from app.services.research_drafts import ResearchDraftService

        def step():
            result = InvestigationCoordinator(engine, settings).run_once(state["evidence_token"])
            if result is None:
                return ResearchDraftService(engine, settings).run_requested_once(state["evidence_token"])
            return result
    else:
        raise RuntimeError("unsupported_worker")
    try:
        while not stop.is_set():
            step()
            stop.wait(2)
    finally:
        engine.dispose()


def setup_workers(state):
    env = clean_env(state)
    os.environ.update(env)
    sys.path.insert(0, env["PYTHONPATH"])
    from app.core.config import Settings
    from app.core.database import make_engine
    from app.models import AssessmentWorker, CSVImportWorker, User
    from app.services.assessment_jobs import AssessmentJobService
    from app.services.csv_imports import CSVImportService
    from app.services.investigation_coordinator import InvestigationCoordinator
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    engine = make_engine(state["database_url"])
    with Session(engine) as session:
        admin = session.scalar(
            select(User.id).where(
                User.username == "windowsadmin", User.active.is_(True), User.role == "admin"
            )
        )
    if admin is None:
        raise RuntimeError("native_admin_required")
    for model, service, name, token in (
        (
            AssessmentWorker,
            AssessmentJobService(engine),
            "native-windows-assessment",
            state["worker_token"],
        ),
        (
            CSVImportWorker,
            CSVImportService(engine, Settings(_env_file=None)),
            "native-windows-import",
            state["import_token"],
        ),
    ):
        with Session(engine) as session:
            prior = session.scalar(select(model).where(model.name == name))
            if prior:
                if (
                    not prior.active
                    or prior.provisioned_by != admin
                    or prior.token_sha256 != hashlib.sha256(token.encode()).hexdigest()
                ):
                    raise RuntimeError("worker_identity_conflict")
                continue
        service.register_worker(admin_id=admin, name=name, token=token)
    InvestigationCoordinator(engine, Settings(_env_file=None)).register_worker(
        admin, "native-windows-evidence", state["evidence_token"]
    )
    engine.dispose()


def supervise():
    directory, state = current()
    discard_stale_supervisor(directory)
    if (directory / "supervisor.json").exists():
        raise RuntimeError("existing_supervisor_record_requires_status_review")
    if (directory / "stop").exists():
        (directory / "stop").unlink()  # Fixed owned control file only; never data/history.
    pg_start(directory, state)
    with connection(state):
        pass
    setup_workers(state)
    env = clean_env(state)
    sys.path.insert(0, env["PYTHONPATH"])
    from app.workers.process_control import WindowsJob, start_in_job

    job = WindowsJob(memory_bytes=8 * 1024**3, cpu_seconds=0, processes=32)
    processes, logs = {}, []
    try:
        for role in ("api", "assessment", "import", "evidence", "frontend"):
            log = (directory / f"{role}.log").open("ab")
            logs.append(log)
            if role == "frontend":
                command = [
                    shutil.which("node.exe"),
                    str(Path(state["source"]) / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(state["frontend_port"]),
                    "--strictPort",
                ]
                cwd = str(Path(state["source"]) / "frontend")
            else:
                command, cwd = (
                    [str(PYTHON), str(Path(__file__).resolve()), "child", "--role", role],
                    state["source"],
                )
            process_env = (
                env
                if role != "frontend"
                else {
                    k: v
                    for k, v in env.items()
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
                        "TRUEFLAG_API_PROXY",
                    }
                }
            )
            p = start_in_job(
                job,
                command,
                cwd=cwd,
                env=process_env,
                stdout=log,
                stderr=log,
            )
            processes[role] = p
        write(
            directory / "supervisor.json",
            {
                "pid": os.getpid(),
                "creation": process_identity(os.getpid()),
                "children": {
                    k: {"pid": v.pid, "creation": process_identity(v.pid)}
                    for k, v in processes.items()
                },
            },
        )
        while not (directory / "stop").exists():
            time.sleep(0.5)
        (directory / "stop").touch()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and any(
            p.poll() is None for k, p in processes.items() if k != "frontend"
        ):
            time.sleep(0.2)
    finally:
        job.terminate()
        for p in processes.values():
            p.wait(timeout=5)
        job.close()
        for log in logs:
            log.close()
        # Application restart must not interrupt the independent acceptance database.
        # PostgreSQL is stopped only by an explicit operator database-stop action.
        if (directory / "supervisor.json").exists():
            (directory / "supervisor.json").unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["initialize", "supervise", "status", "stop", "child", "refresh", "fixtures"],
    )
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--role")
    parser.add_argument("--stop-database", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("native_windows_required")
    if args.action == "initialize":
        initialize(args.pg_bin.resolve(strict=True))
    elif args.action == "refresh":
        directory, state = current()
        if (directory / "supervisor.json").exists():
            raise RuntimeError("stop_before_source_refresh")
        with connection(state):
            pass
        state["source"] = str(stage_source(directory, "source-" + uuid4().hex))
        temporary = directory / ("state-" + uuid4().hex + ".json")
        write(temporary, state)
        temporary.replace(directory / "state.json")
        print('{"status":"source_refreshed","database_unchanged":true}')
    elif args.action == "fixtures":
        directory, state = current()
        with connection(state):
            pass
        env = clean_env(state)
        os.environ.update(env)
        sys.path[:0] = [env["PYTHONPATH"], str(Path(state["source"]) / "scripts")]
        from app.core.database import make_engine
        from native_demo_runtime import actor, fixtures

        engine = make_engine(state["database_url"])
        fixtures(engine, actor(engine, "windowsadmin"))
        engine.dispose()
    elif args.action == "child":
        child(args.role)
    elif args.action == "supervise":
        supervise()
    elif args.action == "stop":
        directory, state = current()
        discard_stale_supervisor(directory)
        (directory / "stop").touch()
        deadline = time.monotonic() + 30
        while (directory / "supervisor.json").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if (directory / "supervisor.json").exists():
            raise RuntimeError("graceful_shutdown_pending")
        if args.stop_database:
            with connection(state) as c:
                active = c.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()"
                ).fetchone()[0]
            if active:
                raise RuntimeError("database_clients_active_stop_refused")
            pg(state, "stop", "-w", "-m", "fast", "-D", str(directory / "data"))
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "data_preserved": True,
                    "database_stopped": args.stop_database,
                }
            )
        )
    else:
        import urllib.request

        directory, state = current()
        status = {
            "frontend": f"http://127.0.0.1:{state['frontend_port']}",
            "api": f"http://127.0.0.1:{state['api_port']}",
            "provider": "disabled",
            "login_file": str(directory / "login.json"),
            "ready": False,
        }
        services = {}
        marker = directory / "supervisor.json"
        if marker.exists():
            for name, record in json.loads(marker.read_text()).get("children", {}).items():
                services[name] = (
                    isinstance(record, dict)
                    and process_identity(record["pid"]) == record["creation"]
                )
        status["services"] = services
        try:
            with urllib.request.urlopen(status["api"] + "/ready", timeout=3) as response:
                status["ready"] = (
                    response.status == 200 and len(services) == 5 and all(services.values())
                )
        except Exception:
            pass
        print(json.dumps(status))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(error).__name__,
                    "frames": [
                        {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                        for f in traceback.extract_tb(error.__traceback__)[-5:]
                    ],
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
