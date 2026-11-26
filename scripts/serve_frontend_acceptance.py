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
    if config.get("investigation_workbench"):
        from sqlalchemy import text

        with owner.connect() as connection:
            actual_cluster = str(
                connection.scalar(text("SELECT system_identifier FROM pg_control_system()"))
            )
            actual_database = connection.scalar(text("SELECT current_database()"))
        assert actual_cluster == config["expected_cluster"] != config["forbidden_cluster"]
        assert actual_database == config["expected_database"] and actual_database.startswith(
            "tf_g0_3_primary_"
        )
    schema = "tf_frontend_acceptance_" + uuid4().hex
    with owner.begin() as connection:
        connection.execute(CreateSchema(schema))
    url = make_url(config["database_url"]).update_query_dict({"options": "-csearch_path=" + schema})
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    engine = server = server_thread = worker_thread = None
    clock_fault = None
    stop = threading.Event()
    enabled = threading.Event()
    fail_next = threading.Event()
    control = Path("/test-control")
    try:
        command.upgrade(Config("backend/alembic.ini"), "head")
        # Many independent browser logins share loopback; leave production defaults unchanged.
        settings = Settings(
            cors_origins=["http://127.0.0.1:15173"],
            login_attempt_limit=100,
            csv_staging_root=Path("/tmp/csv-staging"),
            batch_assessment_dispatch_enabled=True,
            investigation_simulation_enabled=bool(config.get("simulation_drafts")),
            investigation_external_enabled=False,
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

        if not config.get("strict_auth", False):
            auth_routes.issue_token = fixture_issuer
        engine = make_engine(settings.database_url)
        if config.get("investigation_workbench"):
            from sqlalchemy import event

            def sql_diagnostic(context):
                # Fixture-only diagnostics: never persist SQL, parameters or error messages.
                with (control / "database-errors.jsonl").open("a") as output:
                    output.write(
                        json.dumps(
                            {
                                "type": type(context.original_exception).__name__,
                                "sqlstate": getattr(context.original_exception, "sqlstate", None),
                            }
                        )
                        + "\n"
                    )

            event.listen(engine, "handle_error", sql_diagnostic)
            from app.models.snapshot_clock import SnapshotClock
            from app.services.snapshot_clock import ClockUnavailable, SnapshotTime
            from sqlalchemy import func, select

            original_observe = SnapshotTime.observe

            def observed_clock(clock):
                try:
                    return original_observe(clock)
                except ClockUnavailable:
                    # Diagnostic only: preserve the exception and all clock guards.
                    diagnostic = {"type": "ClockUnavailable"}
                    try:
                        with Session(clock.engine) as session:
                            floor = session.get(SnapshotClock, 1)
                            diagnostic.update(
                                now=int(session.scalar(select(func.clock_timestamp())).timestamp()),
                                high_water=floor.high_water,
                                epoch=floor.epoch,
                                regressed=floor.regressed,
                            )
                    except Exception as failure:
                        diagnostic["diagnostic_error_type"] = type(failure).__name__
                    with (control / "clock-errors.jsonl").open("a") as output:
                        output.write(json.dumps(diagnostic) + "\n")
                    raise

            SnapshotTime.observe = observed_clock
            from functools import wraps
            from traceback import extract_tb

            from app.services.evidence import atomic
            from app.services.evidence_read import EvidenceReadService

            def observe_read(method):
                @wraps(method)
                def observed(*args, **kwargs):
                    try:
                        return method(*args, **kwargs)
                    except Exception as error:
                        frames = extract_tb(error.__traceback__)[-4:]
                        with (control / "read-errors.jsonl").open("a") as output:
                            output.write(
                                json.dumps(
                                    {
                                        "type": type(error).__name__,
                                        "frames": [
                                            {
                                                "file": Path(f.filename).name,
                                                "function": f.name,
                                                "line": f.lineno,
                                            }
                                            for f in frames
                                        ],
                                    }
                                )
                                + "\n"
                            )
                        raise

                return observed

            for name in ["calculate_activity", "get_transactions"]:
                method = getattr(EvidenceReadService, name).__wrapped__
                setattr(EvidenceReadService, name, atomic(observe_read(method)))
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
        connected_sources = {}
        case_sources = {}
        if config.get("investigation_workbench"):
            from uuid import UUID

            from app.schemas.cases import AssignmentInput
            from app.services.cases import assign_case
            from app.services.connected_scenarios import scenario_bundle
            from app.services.evidence import EvidenceService

            foundation = EvidenceService(engine)
            scenarios = [
                ("connected", "ordinary", "uianalyst"),
                ("incomplete", "incomplete_history", "uianalyst"),
                ("connected_foreign", "conflicting_kyc", "uiother"),
                ("connected_unassigned", "zero_income", None),
            ]
            if config.get("design_system"):
                scenarios.append(("design", "ordinary", "uianalyst"))
            if config.get("case_workflows"):
                scenarios.append(("workflow", "ordinary", None))
            if config.get("simulation_drafts"):
                scenarios.extend(
                    [
                        ("draft-complete", "ordinary", "uianalyst"),
                        ("draft-incomplete", "incomplete_history", "uianalyst"),
                        ("draft-revoked", "ordinary", "uianalyst"),
                        ("draft-clock", "ordinary", "uianalyst"),
                        ("draft-foreign", "ordinary", "uiother"),
                        ("draft-one-click", "ordinary", "uianalyst"),
                    ]
                )
            for scenario_index, (name, key, assignee) in enumerate(scenarios):
                bundle = scenario_bundle(
                    key,
                    20430 + scenario_index
                    if name.startswith("draft-")
                    else 20263
                    if name == "workflow"
                    else 20262
                    if name == "design"
                    else 20261,
                )
                actor = UUID(user_ids["uiadmin"])
                source = foundation.register_source(actor, bundle.scenario_id)
                release = foundation.admit_version(actor, source, bundle)
                case_id = foundation.create_case(actor, release)
                if assignee:
                    with Session(engine) as session:
                        assign_case(
                            session,
                            actor,
                            case_id,
                            AssignmentInput(
                                expected_version=1, assigned_to=UUID(user_ids[assignee])
                            ),
                        )
                cases[name] = str(case_id)
                connected_sources[name] = source
                with Session(engine) as session:
                    case_sources[name] = session.get(
                        Alert, session.get(Case, case_id).alert_id
                    ).source_id
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
        investigation = None
        drafts = None
        investigation_token = secrets.token_urlsafe(48)
        if config.get("investigation_workbench"):
            from app.services.investigation_coordinator import InvestigationCoordinator

            investigation = InvestigationCoordinator(engine, settings)
            investigation.register_worker(
                UUID(user_ids["uiadmin"]), "browser-evidence-worker", investigation_token
            )
            if config.get("simulation_drafts"):
                from app.services.investigation_drafts import InvestigationDraftService

                drafts = InvestigationDraftService(engine, settings)

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
                        if investigation is not None:
                            investigation.run_once(investigation_token)
                        if drafts is not None:
                            drafts.run_once(investigation_token)
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
                    "case_sources": case_sources,
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
                        if (
                            config.get("investigation_workbench")
                            and request.get("clock_fault") is True
                            and clock_fault is None
                        ):
                            from datetime import datetime, timedelta, timezone

                            from app.models.snapshot_clock import SnapshotClock
                            from app.services.snapshot_clock import SnapshotTime
                            from sqlalchemy import text

                            sys.path.insert(0, "backend/tests")
                            from test_snapshot_clock_integrity import clock_view

                            with Session(engine) as session:
                                instant = max(
                                    session.scalar(text("SELECT clock_timestamp()")),
                                    datetime.fromtimestamp(
                                        session.get(SnapshotClock, 1).high_water, timezone.utc
                                    ),
                                )
                            clock_fault = clock_view(engine, instant)
                            simulated = clock_fault.__enter__()
                            SnapshotTime(engine).observe()
                            simulated[0] = instant - timedelta(seconds=1)
                        if request.get("clock_fault") is False and clock_fault is not None:
                            clock_fault.__exit__(None, None, None)
                            clock_fault = None
                        if (
                            config.get("investigation_workbench")
                            and request.get("revoke_source") in connected_sources
                        ):
                            name = request["revoke_source"]
                            foundation.set_source_access(
                                UUID(user_ids["uiadmin"]),
                                UUID(cases[name]),
                                connected_sources[name],
                                False,
                            )
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
        if clock_fault is not None:
            clock_fault.__exit__(None, None, None)
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
