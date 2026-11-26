"""Persistent upload workspace acceptance using existing synthetic ingestion/import services."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
import test_csv_imports
import test_csv_staging
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_csv_imports import approve, finish, prepare
from test_csv_staging import send
from test_foundation import headers

from app.models import (
    AuditEvent,
    Case,
    CSVUpload,
    UploadSession,
    UploadSessionItem,
    UploadWorkspace,
    User,
)
from app.security.auth import password_hash
from app.services.upload_sessions import UploadSessionService

PATH = "/api/v1/upload-sessions"
upload = test_csv_staging.upload
base_upload = test_csv_staging.upload
imports = test_csv_imports.imports


def state(env, auth=None):
    r = env["client"].get(PATH, headers=auth or env["auth"])
    assert r.status_code == 200, r.text
    return r.json()


def create(env, version, key=None):
    return env["client"].post(
        PATH,
        json={"version": version},
        headers={**env["auth"], "Idempotency-Key": key or str(uuid4())},
    )


def select_session(env, sid, version, auth=None):
    return env["client"].put(
        f"{PATH}/{sid}/selection", json={"version": version}, headers=auth or env["auth"]
    )


def test_empty_workspace_persists_and_hides_non_imported_cases(upload, alert_payload):
    env = upload
    r = env["client"].post(
        "/api/v1/alerts",
        json=alert_payload,
        headers={**env["auth"], "Idempotency-Key": str(uuid4())},
    )
    assert r.status_code == 201
    initial = state(env)
    assert initial["active"]["case_count"] == initial["active"]["upload_count"] == 0
    assert state(env) == initial
    sid = initial["active"]["id"]
    page = env["client"].get(
        f"/api/v1/cases?origin=uploaded&upload_session_id={sid}", headers=env["auth"]
    )
    assert page.status_code == 200 and page.json()["total"] == 0
    # Backwards-compatible direct ingestion API remains usable; its record was not deleted.
    assert env["client"].get("/api/v1/cases", headers=env["auth"]).json()["total"] == 1


def test_upload_is_bound_atomically_and_new_session_keeps_history(upload):
    old = state(upload)
    sid = old["active"]["id"]
    sent = send(upload, extra={"X-Upload-Session-ID": sid})
    assert sent.status_code == 201
    uploaded = state(upload)
    assert uploaded["active"]["upload_count"] == 1
    assert uploaded["active"]["uploads"][0]["resume_route"].endswith(sent.json()["upload_id"])
    new = create(upload, uploaded["version"])
    assert new.status_code == 201
    assert new.json()["active"]["id"] != sid
    assert new.json()["active"]["upload_count"] == 0
    restored = select_session(upload, sid, new.json()["version"])
    assert restored.status_code == 200 and restored.json()["active"]["upload_count"] == 1


def test_request_retry_does_not_reactivate_superseded_session(upload):
    first = state(upload)
    key = str(uuid4())
    second = create(upload, first["version"], key).json()
    third = create(upload, second["version"]).json()
    retry = create(upload, first["version"], key)
    assert retry.status_code == 201 and retry.json()["active"]["id"] == third["active"]["id"]
    assert create(upload, third["version"], key).status_code == 409
    assert create(upload, first["version"]).status_code == 409
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(UploadSession)) == 3


def test_stale_upload_header_cannot_bind_to_another_session(upload):
    initial = state(upload)
    create(upload, initial["version"])
    r = send(upload, extra={"X-Upload-Session-ID": initial["active"]["id"]})
    assert r.status_code == 409
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(CSVUpload)) == 0
    assert list(upload["settings"].csv_staging_root.glob("*.csv")) == []


def test_duplicate_upload_cannot_move_between_sessions(upload):
    first = state(upload)
    assert send(upload).status_code == 201
    new = create(upload, first["version"]).json()
    r = send(upload, extra={"X-Upload-Session-ID": new["active"]["id"]})
    assert r.status_code == 409
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(UploadSessionItem)) == 1


def test_resume_lookup_is_owner_scoped_and_does_not_change_selection(upload, platform):
    old = state(upload)
    receipt = send(upload).json()
    fresh = create(upload, old["version"]).json()
    linked = upload["client"].get(
        f"{PATH}/lookup/upload/{receipt['upload_id']}", headers=upload["auth"]
    )
    assert linked.status_code == 200 and linked.json()["session_id"] == old["active"]["id"]
    assert state(upload)["active"]["id"] == fresh["active"]["id"]
    assert (
        upload["client"].get(f"{PATH}/lookup/upload/{uuid4()}", headers=upload["auth"]).status_code
        == 404
    )
    analyst = headers(platform, "analyst")
    assert (
        upload["client"]
        .get(f"{PATH}/lookup/upload/{receipt['upload_id']}", headers=analyst)
        .status_code
        == 403
    )


def test_unauthorized_and_cross_user_session_isolation(upload, platform):
    own = state(upload)
    assert upload["client"].get(PATH).status_code == 401
    analyst = headers(platform, "analyst")
    assert state(upload, analyst)["active"] is None
    assert select_session(upload, own["active"]["id"], 1, analyst).status_code == 404
    assert (
        upload["client"]
        .post(PATH, json={"version": 1}, headers={**analyst, "Idempotency-Key": str(uuid4())})
        .status_code
        == 403
    )
    with Session(upload["engine"]) as s, s.begin():
        s.add(
            User(
                username="anotheradmin", role="admin", password_hash=password_hash.hash(platform[3])
            )
        )
    other = headers(platform, "anotheradmin")
    assert select_session(upload, own["active"]["id"], 1, other).status_code == 404
    assert (
        upload["client"]
        .get("/api/v1/cases", params={"upload_session_id": own["active"]["id"]}, headers=other)
        .status_code
        == 404
    )


def test_role_revocation_hides_session_and_resume_receipts(upload):
    state(upload)
    send(upload)
    with Session(upload["engine"]) as s, s.begin():
        s.get(User, upload["actor_id"]).role = "analyst"
    r = upload["client"].get(PATH, headers=upload["auth"])
    assert r.status_code == 200 and r.json()["active"] is None and r.json()["items"] == []
    assert create(upload, 1).status_code == 403


@pytest.mark.parametrize(
    "body", [{"version": True}, {"version": 0}, {"version": 1, "actor_id": "forged"}]
)
def test_strict_session_input(upload, body):
    r = upload["client"].post(
        PATH, json=body, headers={**upload["auth"], "Idempotency-Key": str(uuid4())}
    )
    assert r.status_code == 422


def test_session_pagination_and_payload_minimization(upload):
    current = state(upload)
    for _ in range(3):
        current = create(upload, current["version"]).json()
    page = upload["client"].get(PATH + "?offset=1&limit=2", headers=upload["auth"]).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert set(page["items"][0]) == {"id", "created_at"}
    assert "features" not in str(page) and "key_sha256" not in str(page)


def test_session_audit_failure_rolls_back_selection_and_creation(upload, monkeypatch):
    import app.services.upload_sessions as service

    old = state(upload)

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private injected error")

    monkeypatch.setattr(service, "event", fail)
    r = create(upload, old["version"])
    assert r.status_code == 503 and "private" not in r.text
    assert state(upload)["active"]["id"] == old["active"]["id"]
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(UploadSession)) == 1


def test_concurrent_creation_is_idempotent_and_serialized(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock acceptance")
    old = state(upload)
    service = UploadSessionService(upload["engine"])

    def run(key):
        return service.execute(upload["actor_id"], action="create", version=old["version"], key=key)

    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [key, key]))
    assert results[0]["active"]["id"] == results[1]["active"]["id"]
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(UploadSession)) == 2
        assert (
            s.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "upload.session.created")
            )
            == 1
        )


def test_legacy_upload_backfill_excludes_seeds_and_is_repeatable(upload):
    for i in range(3):
        assert send(upload, key=f"legacy-upload-key-{i:04d}").status_code == 201
    # Simulate the pre-migration state: uploads exist but no workspace tables had records.
    with Session(upload["engine"]) as s, s.begin():
        s.execute(delete(UploadWorkspace))
        s.execute(delete(UploadSessionItem))
        s.execute(delete(UploadSession))
    restored = state(upload)
    assert restored["active"]["upload_count"] == 3
    assert restored["active"]["case_count"] == 0
    assert state(upload) == restored
    with Session(upload["engine"]) as s:
        assert s.scalar(select(func.count()).select_from(UploadSessionItem)) == 3


def test_migration_roundtrip_and_retained_history_guard(upload):
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "0018_human_casework")
    assert "upload_sessions" not in inspect(upload["engine"]).get_table_names()
    command.upgrade(config, "head")
    state(upload)
    with pytest.raises(RuntimeError, match="retained upload sessions"):
        command.downgrade(config, "0018_human_casework")
    assert "upload_sessions" in inspect(upload["engine"]).get_table_names()
    assert state(upload)["total"] == 1


def test_real_import_scoping_resume_and_assignment_revocation(imports, platform, alert_payload):
    env = imports
    old = state(env)
    prepared = prepare(env)
    response = approve(env, prepared)
    assert response.status_code == 202
    finish(env)
    current = state(env)
    assert current["active"]["case_count"] == 3
    assert (
        current["active"]["uploads"][0]["resume_route"]
        == "#/batch/import/" + response.json()["import_id"]
    )
    sid = old["active"]["id"]
    # A separately ingested seed must not change this session's totals or filtered pagination.
    seed = env["client"].post(
        "/api/v1/alerts",
        json=alert_payload,
        headers={**env["auth"], "Idempotency-Key": str(uuid4())},
    )
    assert seed.status_code == 201
    page = env["client"].get(
        "/api/v1/case-queue", params={"upload_session_id": sid, "limit": 2}, headers=env["auth"]
    )
    assert page.status_code == 200 and page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    case_id = UUID(page.json()["items"][0]["id"])
    with Session(env["engine"]) as s, s.begin():
        analyst_id = s.scalar(select(User.id).where(User.username == "analyst"))
        s.get(Case, case_id).assigned_to = analyst_id
    analyst = headers(platform, "analyst")
    available = state(env, analyst)
    assert available["active"]["case_count"] == 1
    assert available["active"]["uploads"] == []
    with Session(env["engine"]) as s, s.begin():
        s.get(Case, case_id).assigned_to = None
    assert state(env, analyst)["active"] is None
    denied = env["client"].get(
        "/api/v1/case-queue", params={"upload_session_id": sid}, headers=analyst
    )
    assert denied.status_code == 404
    fresh = create(env, current["version"]).json()
    assert fresh["active"]["case_count"] == 0
    restored = select_session(env, sid, fresh["version"]).json()
    assert restored["active"]["case_count"] == 3
    assert state(env)["active"]["id"] == sid
