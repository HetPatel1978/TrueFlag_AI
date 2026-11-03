"""Private Linux/PG browser fixture. Test controls are mounted files, never HTTP endpoints."""

import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import jwt
import uvicorn
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.database import make_engine
from app.main import create_app
from app.models import Alert, Case, User
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures, AlertIngestionInput
from app.schemas.csv_uploads import COLUMNS
from app.security.auth import password_hash
from app.services.assessment_jobs import AssessmentJobService
from app.services.csv_imports import CSVImportService
from app.services.ingestion import fingerprints
from app.workers.assessment_worker import AssessmentWorker
from app.workers.csv_import_worker import CSVImportWorker
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema


def main():
    config = json.loads(sys.stdin.readline())
    assert (
        sys.platform == "linux"
        and make_url(config["database_url"]).get_backend_name() == "postgresql"
    )
    owner = make_engine(config["database_url"])
    schema = "tf_frontend_acceptance_" + uuid4().hex
    with owner.begin() as connection:
        connection.execute(CreateSchema(schema))
    url = make_url(config["database_url"]).update_query_dict({"options": "-csearch_path=" + schema})
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    engine = server = server_thread = worker_thread = None
    stop = threading.Event()
    enabled = threading.Event()
    fail_next = threading.Event()
    control = Path("/test-control")
    try:
        command.upgrade(Config("backend/alembic.ini"), "head")
        # Many independent browser logins share loopback; leave production defaults unchanged.
        settings = Settings(
            login_attempt_limit=100,
            csv_staging_root=Path("/tmp/csv-staging"),
            batch_assessment_dispatch_enabled=True,
        )
        # Match the existing synthetic fixture's documented Docker guest-clock workaround.
        # Password login/signing/verification/current DB permissions remain the real services.
        # Never change production validation leeway or allow arbitrary/future-issued tokens.
        from app.api import routes as auth_routes

        original_issuer = auth_routes.issue_token

        def fixture_issuer(user, settings):
            token = original_issuer(user, settings)
            claims = jwt.decode(token, options={"verify_signature": False})
            claims["iat"] -= 60
            return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")

        auth_routes.issue_token = fixture_issuer
        engine = make_engine(settings.database_url)
        password = secrets.token_urlsafe(24)
        with Session(engine) as session, session.begin():
            users = {
                name: User(username=name, role=role, password_hash=password_hash.hash(password))
                for name, role in [
                    ("uianalyst", "analyst"),
                    ("uiother", "analyst"),
                    ("uisupervisor", "supervisor"),
                    ("uiadmin", "admin"),
                    ("uibatchadmin", "admin"),
                ]
            }
            session.add_all(users.values())
            session.flush()
            user_ids = {name: str(user.id) for name, user in users.items()}
            cases = {}
            for index in range(24):
                name = (
                    ["alpha", "zero", "foreign", "unassigned"][index]
                    if index < 4
                    else f"page-{index:02}"
                )
                values = {field: 0 for field in AlertFeatures.model_fields}
                values.update(
                    state="QZ",
                    kycRiskScore=4 if index % 2 else 1,
                    income=None if index % 2 else 0,
                    totalSpend90d=17 + index,
                )
                body = AlertIngestionInput(
                    source_id="synthetic-ui-" + name,
                    data_classification="synthetic",
                    feature_contract_version=FEATURE_CONTRACT_VERSION,
                    features=values,
                )
                alert = Alert(
                    source_id=body.source_id,
                    feature_contract_version=FEATURE_CONTRACT_VERSION,
                    features=body.features.model_dump(),
                    input_sha256=fingerprints(body)[0],
                )
                session.add(alert)
                session.flush()
                case = Case(
                    alert_id=alert.id,
                    assigned_to=None
                    if index == 3
                    else users["uiother" if index == 2 else "uianalyst"].id,
                )
                session.add(case)
                session.flush()
                cases[name] = str(case.id)
        queue = AssessmentJobService(engine)
        token = secrets.token_hex(32)
        from uuid import UUID

        queue.register_worker(
            admin_id=UUID(user_ids["uiadmin"]), name="browser-acceptance", token=token
        )
        worker = AssessmentWorker(queue, token, stop)
        import_queue = CSVImportService(engine, settings)
        import_token = secrets.token_hex(32)
        import_queue.register_worker(
            UUID(user_ids["uiadmin"]), "browser-import-worker", import_token
        )
        import_worker = CSVImportWorker(import_queue, import_token)

        def work():
            while not stop.is_set():
                try:
                    import_worker.run_once()
                except Exception:
                    pass
                if enabled.is_set():
                    try:
                        if fail_next.is_set():
                            claim = queue.claim(token)
                            if claim:
                                fail_next.clear()
                                queue.fail(token, claim, "processing_unavailable", retryable=False)
                        else:
                            worker.run_once()
                    except Exception:
                        # Parent acceptance assertions detect nonprogress; no exception data escapes.
                        pass
                stop.wait(0.1)

        app = create_app(settings, engine)
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="0.0.0.0", port=8000, log_config=None, access_log=False, log_level="error"
            )
        )
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        worker_thread = threading.Thread(target=work, daemon=True)
        worker_thread.start()
        deadline = time.monotonic() + 20
        while not server.started and time.monotonic() < deadline:
            stop.wait(0.05)
        assert server.started
        # Captured by the host runner in an ignored file; never printed to tool/user logs.
        print(
            json.dumps(
                {
                    "ready": True,
                    "password": password,
                    "cases": cases,
                    "users": user_ids,
                    "csv_columns": list(COLUMNS),
                    "feature_contract_version": FEATURE_CONTRACT_VERSION,
                }
            ),
            flush=True,
        )

        def eof():
            for _ in sys.stdin:
                pass
            stop.set()

        threading.Thread(target=eof, daemon=True).start()
        sequence = 0
        deadline = time.monotonic() + 600
        while not stop.is_set() and time.monotonic() < deadline:
            for path in sorted(control.glob("command.*.json")):
                try:
                    request = json.loads(path.read_text())
                    if request["sequence"] > sequence:
                        sequence = request["sequence"]
                        if request.get("fail_next"):
                            fail_next.set()
                        if request.get("worker") == "pause":
                            enabled.clear()
                        if request.get("worker") == "start":
                            enabled.set()
                        if request.get("restart_api"):
                            # Exercise real TCP listener/lifespan/dispatcher restart, not a mock response.
                            server.should_exit = True
                            server_thread.join(timeout=10)
                            assert not server_thread.is_alive()
                            app = create_app(settings, engine)
                            server = uvicorn.Server(
                                uvicorn.Config(
                                    app,
                                    host="0.0.0.0",
                                    port=8000,
                                    log_config=None,
                                    access_log=False,
                                    log_level="error",
                                )
                            )
                            server_thread = threading.Thread(target=server.run, daemon=True)
                            server_thread.start()
                            ready_until = time.monotonic() + 10
                            while not server.started and time.monotonic() < ready_until:
                                stop.wait(0.05)
                            assert server.started
                        if request.get("revoke_batch_admin"):
                            with Session(engine) as session, session.begin():
                                session.get(
                                    User, UUID(user_ids["uibatchadmin"])
                                ).role = "supervisor"
                        target = control / f"ack.{sequence}.json"
                        target.write_text(json.dumps({"sequence": sequence}))
                except (ValueError, KeyError, OSError):
                    pass
            stop.wait(0.05)
        return 0
    finally:
        stop.set()
        if worker_thread:
            worker_thread.join(timeout=45)
        if server:
            server.should_exit = True
        if server_thread:
            server_thread.join(timeout=5)
        if engine:
            engine.dispose()
        with owner.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        owner.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"ready": False, "reason": "frontend_acceptance_failed"}), flush=True)
        raise SystemExit(1) from None
