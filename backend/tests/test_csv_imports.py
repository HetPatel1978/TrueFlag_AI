"""Synthetic PostgreSQL import acceptance; Linux process death and fenced restart."""

import json
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import test_csv_staging
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_csv_validation import data, staged, validate
from test_foundation import headers

from app.models import (
    Alert,
    AlertIngestion,
    AssessmentJob,
    AuditEvent,
    Case,
    CSVImport,
    CSVImportRow,
    CSVUpload,
    CSVValidation,
    CSVValidationIssue,
    User,
)
from app.services.csv_imports import (
    CSVImportService,
    ImportClaim,
    ImportLeaseLost,
    ImportUnavailable,
    ImportWorkerDenied,
)
from app.services.csv_staging import UploadDenied

base_upload = test_csv_staging.upload


@pytest.fixture
def imports(base_upload):
    env = base_upload
    if env["engine"].dialect.name != "postgresql":
        pytest.skip("durable imports require PostgreSQL")
    env["settings"].csv_import_chunk_size = 2
    env["queue"] = CSVImportService(env["engine"], env["settings"])
    env["token"] = secrets.token_hex(32)
    env["worker_id"] = env["queue"].register_worker(
        env["actor_id"], "synthetic-import-worker", env["token"]
    )
    return env


def prepare(env, rows=None):
    uid = staged(
        env,
        data(
            [{}, {"income": "0"}, {"income": "bad"}, {"income": "2.5e2"}] if rows is None else rows
        ),
    )
    response = validate(env, uid)
    assert response.status_code == 201, response.text
    preview = response.json()
    approval = {
        n: preview[n]
        for n in (
            "upload_sha256",
            "mapping_sha256",
            "mapping_version",
            "validator_version",
            "units",
        )
    }
    approval.update(approve_valid_rows=True, validation_version=preview["version"])
    return uid, preview, approval


def approve(env, prepared=None, key=None, auth=None, body=None):
    uid, preview, approval = prepared or prepare(env)
    response = env["client"].post(
        f"/api/v1/batch-uploads/{uid}/validations/{preview['validation_id']}/imports",
        json=approval if body is None else body,
        headers={
            **(env["auth"] if auth is None else auth),
            "Idempotency-Key": key or "import-key-" + uuid4().hex,
        },
    )
    return response


def total(env, model):
    with Session(env["engine"]) as session:
        return session.scalar(select(func.count()).select_from(model))


def finish(env):
    results = []
    for _ in range(20):
        claim = env["queue"].claim(env["token"])
        if claim is None:
            break
        results.append(env["queue"].process_chunk(env["token"], claim))
    return results


def due(env, import_id):
    with Session(env["engine"]) as session, session.begin():
        row = session.get(CSVImport, UUID(str(import_id)))
        row.available_at = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)


def test_approval_chunk_progress_invalid_exclusion_features_and_receipts(imports, caplog):
    env = imports
    prepared = prepare(env)
    response = approve(env, prepared, key="stable-synthetic-import-key")
    assert response.status_code == 202, response.text
    initial = response.json()
    assert initial["status"] == "pending" and initial["unprocessed_rows"] == 4
    assert total(env, Alert) == total(env, Case) == 0
    claim = env["queue"].claim(env["token"])
    assert (
        env["client"].get(response.headers["location"], headers=env["auth"]).json()["status"]
        == "running"
    )
    first = env["queue"].process_chunk(env["token"], claim)
    assert first.status == "pending" and first.processed_rows == first.created_rows == 2
    assert total(env, CSVImportRow) == 2
    last = finish(env)[-1]
    assert (
        last.status,
        last.processed_rows,
        last.created_rows,
        last.excluded_rows,
        last.invalid_rows,
    ) == ("partially_completed", 4, 3, 1, 1)
    assert total(env, Alert) == total(env, Case) == total(env, AlertIngestion) == 3
    assert total(env, AssessmentJob) == 0
    assert env["queue"].claim(env["token"]) is None
    progress = env["client"].get(response.headers["location"], headers=env["auth"])
    assert progress.status_code == 200 and progress.json()["created_rows"] == 3
    page = (
        env["client"]
        .get(response.headers["location"] + "/rows?offset=1&limit=2", headers=env["auth"])
        .json()
    )
    assert page["total"] == 4 and [r["row_number"] for r in page["items"]] == [3, 4]
    assert page["items"][1]["status"] == "invalid" and page["items"][1]["case_id"] is None
    assert page["items"][1]["errors"] == [{"field": "income", "code": "number_format"}]
    with Session(env["engine"]) as session:
        rows = session.scalars(select(Alert).order_by(Alert.source_id)).all()
        assert [r.features["income"] for r in rows] == [None, 0, 250.0]
        assert all(len(r.features) == 27 for r in rows)
        assert all(
            r.status == "open" and r.disposition is None for r in session.scalars(select(Case))
        )
        assert session.scalar(
            select(AuditEvent.id).where(AuditEvent.action == "batch.import.completed")
        )
    replay = approve(env, prepared, key="stable-synthetic-import-key")
    assert replay.status_code == 202 and replay.json()["import_id"] == initial["import_id"]
    assert "preview-synthetic-" not in response.text + progress.text + str(page) + caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("approve_valid_rows", False),
        ("approve_valid_rows", 1),
        ("units", "USD"),
        ("mapping_version", "unknown"),
        ("validation_version", True),
    ],
)
def test_explicit_approval_contract_strict(imports, field, value):
    prepared = prepare(imports)
    body = dict(prepared[2])
    body[field] = value
    assert approve(imports, prepared, body=body).status_code == 422
    assert total(imports, CSVImport) == total(imports, Alert) == 0


@pytest.mark.parametrize("field", ["upload_sha256", "mapping_sha256", "validation_version"])
def test_stale_approval_hash_or_version_conflicts(imports, field):
    prepared = prepare(imports)
    body = dict(prepared[2])
    body[field] = 99 if field == "validation_version" else "0" * 64
    assert approve(imports, prepared, body=body).status_code == 409
    assert total(imports, CSVImport) == 0


def test_key_conflicts_one_import_per_preview_and_zero_valid_rejection(imports):
    prepared = prepare(imports)
    first = approve(imports, prepared, key="fixed-import-approval-001")
    assert first.status_code == 202
    assert approve(imports, prepared, key="different-import-approval").status_code == 409
    changed = dict(prepared[2])
    changed["upload_sha256"] = "0" * 64
    assert (
        approve(imports, prepared, key="fixed-import-approval-001", body=changed).status_code == 409
    )
    invalid = prepare(imports, [{"income": "bad"}])
    assert approve(imports, invalid).status_code == 422
    assert total(imports, CSVImport) == 1


def test_identical_existing_sources_reused_conflicts_not_overwritten(imports):
    first = approve(imports, prepare(imports, [{}, {"income": "0"}]))
    assert first.status_code == 202
    initial_results = finish(imports)
    assert initial_results and initial_results[-1].status == "completed"
    assert initial_results[-1].created_rows == 2
    with Session(imports["engine"]) as session, session.begin():
        original = session.scalar(select(Alert).where(Alert.source_id == "preview-synthetic-0"))
        case = session.scalar(select(Case).where(Case.alert_id == original.id))
        case.status = "closed"
        case.disposition = "close"
        case.assigned_to = session.scalar(select(User.id).where(User.username == "analyst"))
        old_id = case.id
    second = approve(
        imports, prepare(imports, [{}, {"income": "999"}, {"source_id": "new-synthetic-source"}])
    )
    assert second.status_code == 202
    result = finish(imports)[-1]
    assert (result.created_rows, result.reused_rows, result.conflict_rows, result.status) == (
        1,
        1,
        1,
        "partially_completed",
    )
    assert total(imports, Case) == 3
    with Session(imports["engine"]) as session:
        existing = session.get(Case, old_id)
        assert (
            existing.status == "closed" and existing.disposition == "close" and existing.assigned_to
        )
        assert (
            session.scalar(select(Alert).where(Alert.source_id == "preview-synthetic-1")).features[
                "income"
            ]
            == 0
        )


def test_duplicate_sources_in_file_excluded(imports):
    assert (
        approve(imports, prepare(imports, [{}, {"source_id": "preview-synthetic-0"}])).status_code
        == 202
    )
    final = finish(imports)[-1]
    assert final.created_rows == 1 and final.excluded_rows == 1 and total(imports, Case) == 1


def test_concurrent_approval_and_exclusive_claim(imports):
    prepared = prepare(imports, [{}, {}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(
                lambda _: approve(imports, prepared, key="concurrent-import-key-001"), range(2)
            )
        )
    assert [r.status_code for r in replies] == [202, 202]
    assert len({r.json()["import_id"] for r in replies}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: imports["queue"].claim(imports["token"]), range(2)))
    assert sum(c is not None for c in claims) == 1
    imports["queue"].process_chunk(imports["token"], next(c for c in claims if c))
    assert total(imports, Case) == 2


def test_cross_user_isolation_unauthorized_and_case_scope(imports, platform):
    prepared = prepare(imports, [{}])
    assert approve(imports, prepared, auth={}).status_code == 401
    analyst = headers(platform, "analyst")
    assert approve(imports, prepared, auth=analyst).status_code == 403
    reply = approve(imports, prepared)
    with Session(imports["engine"]) as session, session.begin():
        owner = session.get(User, imports["actor_id"])
        session.add(User(username="importadmin", role="admin", password_hash=owner.password_hash))
    other = headers(platform, "importadmin")
    for suffix in ("", "/rows"):
        path = reply.headers["location"] + suffix
        assert imports["client"].get(path).status_code == 401
        assert imports["client"].get(path, headers=analyst).status_code == 403
        assert imports["client"].get(path, headers=other).status_code == 404
    assert approve(imports, prepared, auth=other).status_code == 404
    finish(imports)
    for query in ("?limit=101", "?offset=-1", "?status=unknown"):
        assert (
            imports["client"]
            .get(reply.headers["location"] + "/rows" + query, headers=imports["auth"])
            .status_code
            == 422
        )


def test_revocation_between_chunks_keeps_prior_commits(imports):
    response = approve(imports, prepare(imports, [{}, {}, {}]))
    first = imports["queue"].claim(imports["token"])
    imports["queue"].process_chunk(imports["token"], first)
    with Session(imports["engine"]) as session, session.begin():
        session.get(User, imports["actor_id"]).role = "analyst"
    claim = imports["queue"].claim(imports["token"])
    with pytest.raises(UploadDenied):
        imports["queue"].process_chunk(imports["token"], claim)
    result = imports["queue"].fail(
        imports["token"], claim, "authorization_changed", retryable=False
    )
    assert result.status == "failed" and result.created_rows == 2 and result.unprocessed_rows == 1
    assert (
        imports["client"].get(response.headers["location"], headers=imports["auth"]).status_code
        == 403
    )
    assert total(imports, Case) == 2


def test_worker_permission_and_revocation(imports):
    approve(imports, prepare(imports, [{}]))
    with pytest.raises(ImportWorkerDenied):
        imports["queue"].claim("not-a-credential")
    claim = imports["queue"].claim(imports["token"])
    imports["queue"].revoke_worker(imports["actor_id"], imports["worker_id"])
    with pytest.raises(ImportWorkerDenied):
        imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Case) == 0


def test_expired_lease_recovery_and_stale_worker_fencing(imports):
    approve(imports, prepare(imports, [{}]))
    claim = imports["queue"].claim(imports["token"])
    with Session(imports["engine"]) as session, session.begin():
        session.get(CSVImport, claim.import_id).lease_until = session.scalar(
            select(func.clock_timestamp())
        ) - timedelta(seconds=1)
    assert imports["queue"].recover_expired(imports["token"]) == 1
    with pytest.raises(ImportLeaseLost):
        imports["queue"].process_chunk(imports["token"], claim)
    due(imports, claim.import_id)
    new = imports["queue"].claim(imports["token"])
    assert new.lease_token != claim.lease_token
    imports["queue"].process_chunk(imports["token"], new)
    with pytest.raises(ImportLeaseLost):
        imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Case) == 1


def test_chunk_database_failure_rolls_back_all_writes(imports):
    response = approve(imports, prepare(imports, [{}, {}]))
    claim = imports["queue"].claim(imports["token"])
    with imports["engine"].begin() as c:
        c.execute(
            text(
                "CREATE FUNCTION fail_import() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.row_number=3 THEN RAISE EXCEPTION 'private_db_details'; END IF; RETURN NEW; END; $$"
            )
        )
        c.execute(
            text(
                "CREATE TRIGGER fail_import BEFORE INSERT ON csv_import_rows FOR EACH ROW EXECUTE FUNCTION fail_import()"
            )
        )
    with pytest.raises(ImportUnavailable):
        imports["queue"].process_chunk(imports["token"], claim)
    for model in (Alert, Case, AlertIngestion, CSVImportRow):
        assert total(imports, model) == 0
    progress = imports["queue"].get(imports["actor_id"], UUID(response.json()["import_id"]))
    assert progress.processed_rows == 0 and progress.status == "running"
    with imports["engine"].begin() as c:
        c.execute(text("DROP TRIGGER fail_import ON csv_import_rows"))
    imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Case) == 2


def test_capacity_and_retry_limits_fail_safely(imports):
    imports["settings"].csv_import_queue_capacity = 1
    first = approve(imports, prepare(imports, [{}]))
    assert first.status_code == 202
    prepared = prepare(imports, [{"source_id": "other-synthetic"}])
    assert approve(imports, prepared).status_code == 429
    iid = UUID(first.json()["import_id"])
    for i in range(3):
        claim = imports["queue"].claim(imports["token"])
        result = imports["queue"].fail(imports["token"], claim, "processing_unavailable")
        assert result.attempts == i + 1
        if i < 2:
            assert result.status == "pending"
            assert imports["queue"].claim(imports["token"]) is None
            due(imports, iid)
    assert result.status == "failed" and result.unprocessed_rows == 1 and total(imports, Case) == 0


def test_approval_freezes_preview_source_identity_and_row_history(imports):
    prepared = prepare(imports, [{}])
    reply = approve(imports, prepared)
    iid = UUID(reply.json()["import_id"])
    uid = UUID(prepared[0])
    vid = UUID(prepared[1]["validation_id"])
    changes = [
        (CSVImport, iid, "snapshot", {}),
        (CSVUpload, uid, "sha256", "0" * 64),
        (CSVValidation, vid, "valid_rows", 0),
    ]
    for model, key, field, value in changes:
        with Session(imports["engine"]) as session:
            with pytest.raises(SQLAlchemyError):
                setattr(session.get(model, key), field, value)
                session.commit()
    with Session(imports["engine"]) as session:
        with pytest.raises(SQLAlchemyError):
            session.add(
                CSVValidationIssue(
                    validation_id=vid,
                    row_number=2,
                    invalid=True,
                    has_warnings=False,
                    errors=[],
                    warnings=[],
                )
            )
            session.commit()
    finish(imports)
    with Session(imports["engine"]) as session:
        with pytest.raises(SQLAlchemyError):
            session.get(CSVImportRow, (iid, 2)).status = "conflict"
            session.commit()


def test_tampering_and_expired_file_fail_without_new_cases(imports):
    prepared = prepare(imports, [{}])
    reply = approve(imports, prepared)
    claim = imports["queue"].claim(imports["token"])
    with Session(imports["engine"]) as session:
        upload = session.get(CSVUpload, UUID(prepared[0]))
        path = imports["settings"].csv_staging_root / upload.storage_key
    path.write_bytes(b"not,the,approved,bytes\n")
    with pytest.raises(ImportUnavailable):
        imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Case) == 0
    # Existing approval receipts and progress remain retrievable independently of private bytes.
    assert (
        imports["client"].get(reply.headers["location"], headers=imports["auth"]).status_code == 200
    )


def test_real_linux_worker_processes_import(imports):
    if sys.platform != "linux":
        pytest.skip("controlled Linux worker")
    from app.workers.csv_import_worker import CSVImportWorker

    approve(imports, prepare(imports, [{}, {}]))
    result = CSVImportWorker(imports["queue"], imports["token"]).run_once()
    assert result.status == "completed" and result.created_rows == 2
    assert total(imports, AssessmentJob) == 0


def test_case_authorization_is_applied_to_row_links(imports, monkeypatch):
    from sqlalchemy import false

    import app.services.csv_imports as module

    reply = approve(imports, prepare(imports, [{}]))
    finish(imports)
    monkeypatch.setattr(module, "visible_cases", lambda user: false())
    response = imports["client"].get(reply.headers["location"] + "/rows", headers=imports["auth"])
    assert response.status_code == 403 and "case_id" not in response.text


def test_approval_rechecks_current_role_after_http_dependency(imports, monkeypatch):
    import app.api.csv_imports as routes

    prepared = prepare(imports, [{}])
    original = routes.CSVImportService

    def revoke(engine, settings):
        with Session(engine) as session, session.begin():
            session.get(User, imports["actor_id"]).role = "analyst"
        return original(engine, settings)

    monkeypatch.setattr(routes, "CSVImportService", revoke)
    assert approve(imports, prepared).status_code == 403
    assert total(imports, CSVImport) == 0


def test_expiry_stops_execution_but_keeps_approval_and_history(imports, monkeypatch):
    import app.services.csv_staging as staging_module

    prepared = prepare(imports, [{}])
    response = approve(imports, prepared, key="expiry-stable-approval-key")
    claim = imports["queue"].claim(imports["token"])
    clock = staging_module._now
    monkeypatch.setattr(staging_module, "_now", lambda session: clock(session) + timedelta(days=10))
    from app.services.csv_staging import UploadExpired

    with pytest.raises(UploadExpired):
        imports["queue"].process_chunk(imports["token"], claim)
    result = imports["queue"].fail(imports["token"], claim, "source_expired", retryable=False)
    assert result.status == "failed" and result.unprocessed_rows == 1
    replay = approve(imports, prepared, key="expiry-stable-approval-key")
    assert replay.status_code == 202 and replay.json()["import_id"] == response.json()["import_id"]
    assert (
        imports["client"].get(response.headers["location"], headers=imports["auth"]).status_code
        == 200
    )
    assert total(imports, Case) == 0


def test_chunk_deadline_rolls_back_and_retries(imports, monkeypatch):
    import app.services.csv_imports as module

    approve(imports, prepare(imports, [{}]))
    claim = imports["queue"].claim(imports["token"])
    ticks = iter([0, 100])
    with monkeypatch.context() as patch:
        patch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
        with pytest.raises(module.ImportTimeout):
            imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Alert) == 0
    result = imports["queue"].fail(imports["token"], claim, "chunk_timeout")
    assert result.status == "pending"


def test_distinct_admin_imports_share_source_constraints(imports, platform, monkeypatch):
    first_prepared = prepare(imports, [{}])
    first = approve(imports, first_prepared)
    with Session(imports["engine"]) as session, session.begin():
        owner = session.get(User, imports["actor_id"])
        other = User(username="secondimportadmin", role="admin", password_hash=owner.password_hash)
        session.add(other)
        session.flush()
        other_id = other.id
    second = dict(imports)
    second["auth"] = headers(platform, "secondimportadmin")
    second["actor_id"] = other_id
    reply = approve(second, prepare(second, [{}]))
    assert first.status_code == reply.status_code == 202
    # This test exercises the source uniqueness race, not clock eligibility.
    # A normal queue poll may return None (not due / SKIP LOCKED); never pass
    # that sentinel to process_chunk as though it were an authenticated claim.
    with Session(imports["engine"]) as session:
        eligible_at = session.scalar(select(func.max(CSVImport.available_at)))
    assert eligible_at is not None
    claim_time = eligible_at + timedelta(seconds=1)
    monkeypatch.setattr("app.services.csv_imports._now", lambda _: claim_time)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: imports["queue"].claim(imports["token"]), range(2)))
    assert all(type(claim) is ImportClaim for claim in claims)
    assert len({claim.import_id for claim in claims}) == 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda claim: imports["queue"].process_chunk(imports["token"], claim), claims)
        )
    assert sum(r.created_rows for r in results) == 1 and sum(r.reused_rows for r in results) == 1
    assert total(imports, Case) == 1


def test_final_fence_rolls_back_chunk_if_lease_elapsed(imports, monkeypatch):
    import app.services.csv_imports as module

    approve(imports, prepare(imports, [{}]))
    claim = imports["queue"].claim(imports["token"])
    clock = module._now
    count = 0

    def expire(session):
        nonlocal count
        count += 1
        return clock(session) + (timedelta(days=1) if count > 1 else timedelta())

    monkeypatch.setattr(module, "_now", expire)
    with pytest.raises(ImportLeaseLost):
        imports["queue"].process_chunk(imports["token"], claim)
    assert total(imports, Case) == total(imports, CSVImportRow) == 0


def test_large_file_commits_bounded_chunks_and_complete_counts(imports):
    imports["settings"].csv_import_chunk_size = 25
    reply = approve(imports, prepare(imports, [{} for _ in range(125)]))
    assert reply.status_code == 202
    results = finish(imports)
    assert len(results) == 5 and [r.processed_rows for r in results] == [25, 50, 75, 100, 125]
    assert results[-1].status == "completed" and total(imports, Case) == 125


def test_approval_audit_failure_rolls_back_queue(imports):
    prepared = prepare(imports, [{}])
    with imports["engine"].begin() as c:
        c.execute(
            text(
                "CREATE FUNCTION fail_import_approval() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='batch.import.approved' THEN RAISE EXCEPTION 'private_approval_error'; END IF; RETURN NEW; END; $$"
            )
        )
        c.execute(
            text(
                "CREATE TRIGGER fail_import_approval BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION fail_import_approval()"
            )
        )
    response = approve(imports, prepared)
    assert response.status_code == 503 and "private_approval_error" not in response.text
    assert total(imports, CSVImport) == 0


def test_approval_rejects_duplicate_keys_and_oversized_json(imports):
    uid, preview, approval = prepare(imports, [{}])
    url = f"/api/v1/batch-uploads/{uid}/validations/{preview['validation_id']}/imports"
    body = json.dumps(approval)[:-1] + ',"approve_valid_rows":true}'
    auth = {
        **imports["auth"],
        "Idempotency-Key": "duplicate-approval-key-001",
        "Content-Type": "application/json",
    }
    assert imports["client"].post(url, content=body, headers=auth).status_code == 422
    assert imports["client"].post(url, content=b"x" * 65537, headers=auth).status_code == 413
    assert total(imports, CSVImport) == 0


def test_database_disconnect_preserves_prior_chunks_and_resumes(imports, monkeypatch):
    imports["settings"].csv_import_chunk_size = 1
    approve(imports, prepare(imports, [{}, {}, {}]))
    claim = imports["queue"].claim(imports["token"])
    imports["queue"].process_chunk(imports["token"], claim)
    current = imports["queue"].claim(imports["token"])
    original = imports["queue"]._ingest

    def disconnect(session, *args):
        result = original(session, *args)
        backend_id = session.scalar(text("SELECT pg_backend_pid()"))
        with imports["engine"].begin() as control:
            assert control.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": backend_id})
        return result

    with monkeypatch.context() as patch:
        patch.setattr(imports["queue"], "_ingest", disconnect)
        with pytest.raises(ImportUnavailable):
            imports["queue"].process_chunk(imports["token"], current)
    assert total(imports, Case) == total(imports, CSVImportRow) == 1
    imports["queue"].fail(imports["token"], current, "database_unavailable")
    due(imports, current.import_id)
    final = finish(imports)[-1]
    assert final.status == "completed" and final.created_rows == 3 and total(imports, Case) == 3


@pytest.mark.parametrize("after_commit", [False, True])
def test_real_linux_process_death_and_restart(imports, after_commit):
    if sys.platform != "linux":
        pytest.skip("real Linux OS process death")
    prepared = prepare(imports, [{}, {}, {}])
    reply = approve(imports, prepared)
    iid = UUID(reply.json()["import_id"])
    due(imports, iid)
    child = r"""
import json,os,sys,secrets,time
from app.core.config import Settings
from app.core.database import make_engine
from app.services.csv_imports import CSVImportService
cfg=json.loads(sys.stdin.read())
settings=Settings(_env_file=None,jwt_secret=secrets.token_urlsafe(48),database_url=cfg['url'],csv_staging_root=cfg['root'],csv_import_chunk_size=2)
queue=CSVImportService(make_engine(cfg['url']),settings)
deadline=time.monotonic()+5
claim=None
while claim is None and time.monotonic()<deadline:
    claim=queue.claim(cfg['token'])
    if claim is None:
        time.sleep(0.02)
if claim is None:
    os._exit(20)
if not cfg['after_commit']:
    original=queue._ingest
    def die(*args):
        result=original(*args)
        os._exit(19)
    queue._ingest=die
try:
    queue.process_chunk(cfg['token'],claim)
except Exception as error:
    print(json.dumps({'failure_stage':'process_chunk','failure_type':type(error).__name__}),flush=True)
    os._exit(21)
os._exit(19)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", child],
        input=json.dumps(
            {
                "url": imports["engine"].url.render_as_string(hide_password=False),
                "root": str(imports["settings"].csv_staging_root),
                "token": imports["token"],
                "after_commit": after_commit,
            }
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=25,
    )
    assert result.returncode == 19, (result.returncode, result.stdout)
    progress = imports["queue"].get(imports["actor_id"], iid)
    if after_commit:
        assert progress.processed_rows == progress.created_rows == 2
    else:
        assert progress.processed_rows == 0 and total(imports, Case) == 0
        with Session(imports["engine"]) as session, session.begin():
            session.get(CSVImport, iid).lease_until = session.scalar(
                select(func.clock_timestamp())
            ) - timedelta(seconds=1)
        assert imports["queue"].recover_expired(imports["token"]) == 1
        due(imports, iid)
    last = finish(imports)[-1]
    assert last.status == "completed" and last.created_rows == 3
    assert total(imports, Case) == total(imports, CSVImportRow) == 3
