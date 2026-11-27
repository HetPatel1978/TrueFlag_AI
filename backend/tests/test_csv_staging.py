"""Synthetic CSV transport/security tests; PostgreSQL concurrency and fault acceptance."""

import csv
import hashlib
import io
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_foundation import headers

from app.models import Alert, AssessmentJob, AuditEvent, Case, CSVUpload, User
from app.schemas.alerts import AlertFeatures, AlertIngestionInput
from app.schemas.csv_uploads import COLUMNS, csv_template
from app.services.csv_staging import (
    CSVStagingService,
    IncomingCSV,
    StagingUnavailable,
    UploadDenied,
    UploadExpired,
    UploadNotFound,
)

PATH = "/api/v1/batch-uploads"
KEY = "synthetic-upload-key-0001"


def sample(source="synthetic-csv-001", income=""):
    values = {name: "0" for name in AlertFeatures.model_fields}
    values.update(state="QZ", kycRiskScore="3", income=income)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerow([source, "synthetic", "datarobot_provisional_v1", *values.values()])
    return output.getvalue().encode("utf-8")


@pytest.fixture
def upload(platform, tmp_path):
    client, engine, settings, _ = platform
    settings.csv_staging_root = tmp_path / "csv-staging"
    auth = headers(platform)
    with Session(engine) as session:
        actor_id = session.scalar(select(User.id).where(User.username == "admin"))
    return {
        "client": client,
        "engine": engine,
        "settings": settings,
        "auth": auth,
        "actor_id": actor_id,
        "service": CSVStagingService(engine, settings),
    }


def send(upload, data=None, key=KEY, auth=None, media="text/csv", extra=None):
    return upload["client"].post(
        PATH,
        content=sample() if data is None else data,
        headers={
            **(upload["auth"] if auth is None else auth),
            "Content-Type": media,
            "Idempotency-Key": key,
            **(extra or {}),
        },
    )


def files(upload):
    root = upload["settings"].csv_staging_root
    return list(root.iterdir()) if root.exists() else []


def total(upload):
    with Session(upload["engine"]) as session:
        return session.scalar(select(func.count()).select_from(CSVUpload))


def test_generated_contract_template_and_exact_feature_semantics(upload):
    response = upload["client"].get(PATH + "/template", headers=upload["auth"])
    assert response.status_code == 200 and response.content == csv_template()
    assert (
        response.headers["content-disposition"] == 'attachment; filename="trueflag-alerts-v1.csv"'
    )
    assert tuple(next(csv.reader(io.StringIO(response.text)))) == tuple(
        n for n in AlertIngestionInput.model_fields if n != "features"
    ) + tuple(AlertFeatures.model_fields)
    assert len(COLUMNS) == 30
    contract = upload["client"].get(PATH + "/contract", headers=upload["auth"]).json()
    assert [p["name"] for p in contract["predictors"]] == list(AlertFeatures.model_fields)
    assert contract["missing_values"] == {"income": [""]}
    assert len([p for p in contract["predictors"] if p["required"]]) == 27


def test_staging_metadata_digest_private_bytes_and_no_canonical_writes(upload, caplog):
    data = sample()
    response = send(upload, data)
    assert (
        response.status_code == 201
        and response.headers["location"] == PATH + "/" + response.json()["upload_id"]
    )
    body = response.json()
    assert body["status"] == "staged" and body["row_count"] == 1 and body["column_count"] == 30
    assert body["size_bytes"] == len(data) and body["sha256"] == hashlib.sha256(data).hexdigest()
    assert not {"storage_key", "headers", "actor_id", "features", "filename"} & set(body)
    assert response.headers["cache-control"] == "no-store"
    with Session(upload["engine"]) as session:
        row = session.get(CSVUpload, UUID(body["upload_id"]))
        assert row.storage_key == row.id.hex + ".csv" and row.actor_id == upload["actor_id"]
        audit = session.get(AuditEvent, row.audit_event_id)
        assert audit.action == "batch.upload.staged"
        assert set(audit.details) == {
            "upload_id",
            "size_bytes",
            "rows",
            "columns",
            "csv_contract_version",
        }
        for model in (Alert, Case, AssessmentJob):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    with upload["service"].open_for_validation(
        upload["actor_id"], UUID(body["upload_id"])
    ) as reader:
        assert reader.read() == data
    assert "synthetic-csv-001" not in response.text and "synthetic-csv-001" not in caplog.text
    assert len(files(upload)) == 1
    if os.name != "nt":
        assert stat.S_IMODE(files(upload)[0].stat().st_mode) == 0o600
        assert stat.S_IMODE(upload["settings"].csv_staging_root.stat().st_mode) == 0o700


@pytest.mark.parametrize("endpoint", ["", "/template", "/contract", "/" + str(uuid4())])
def test_csv_endpoints_reject_anonymous_and_analysts(upload, platform, endpoint):
    if endpoint:
        anonymous = upload["client"].get(PATH + endpoint)
        denied = upload["client"].get(PATH + endpoint, headers=headers(platform, "analyst"))
    else:
        anonymous = send(upload, auth={})
        denied = send(upload, auth=headers(platform, "analyst"))
    assert anonymous.status_code == 401 and denied.status_code == 403
    assert total(upload) == 0 and files(upload) == []


def test_supervisor_and_other_admin_cannot_read_an_owners_upload(upload, platform):
    with Session(upload["engine"]) as session, session.begin():
        primary = session.scalar(select(User).where(User.username == "admin"))
        session.add_all(
            [
                User(username="csvother", role="admin", password_hash=primary.password_hash),
                User(
                    username="csvsupervisor", role="supervisor", password_hash=primary.password_hash
                ),
            ]
        )
    owned = send(upload).json()["upload_id"]
    assert send(upload, auth=headers(platform, "csvsupervisor")).status_code == 403
    foreign = headers(platform, "csvother")
    denied = upload["client"].get(PATH + "/" + owned, headers=foreign)
    missing = upload["client"].get(PATH + "/" + str(uuid4()), headers=foreign)
    assert denied.status_code == missing.status_code == 404 and denied.json() == missing.json()
    # Same bytes/key, different actor: distinct intent and receipt, no global digest deduplication.
    other = send(upload, auth=foreign)
    assert other.status_code == 201 and other.json()["upload_id"] != owned


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xef\xbb\xbf",
        b"source_id,income\n",
        b"income,income\n1,2\n",
        b"Income,income\n1,2\n",
        b"source_id,,income\nx,y,z\n",
        b"=formula,income\nx,0\n",
        b'"private\nheader",income\nx,0\n',
        b'one,two\n"unterminated\n',
        "one,two\nx,cafe\n".encode("utf-16"),
        b"one,two\nx,caf\xe9\n",
        b"one,two\nx,\x00\n",
        b"%PDF-private\nbody\n",
        b"PK\x03\x04fake-zip\ndata\n",
    ],
)
def test_invalid_or_empty_csv_is_rejected_without_residue(upload, data):
    response = send(upload, data)
    assert response.status_code == 422 and total(upload) == 0 and files(upload) == []
    assert "private" not in response.text and "cafe" not in response.text


@pytest.mark.parametrize(
    "media",
    [
        "application/json",
        "application/octet-stream",
        "multipart/form-data",
        "text/plain",
        "text/csv;charset=iso-8859-1",
    ],
)
def test_non_csv_media_types_are_rejected(upload, media):
    assert send(upload, media=media).status_code == 415
    assert files(upload) == []


def test_encoding_filename_and_path_controls(upload):
    assert send(upload, extra={"Content-Encoding": "gzip"}).status_code == 415
    assert send(upload, extra={"X-Upload-Filename": "../../private.csv"}).status_code == 422
    assert (
        send(
            upload, extra={"Content-Disposition": 'attachment; filename="private-person.csv"'}
        ).status_code
        == 422
    )
    assert (
        upload["client"]
        .post(
            PATH + "?path=../../private.csv",
            content=sample(),
            headers={**upload["auth"], "Content-Type": "text/csv", "Idempotency-Key": KEY},
        )
        .status_code
        == 422
    )
    assert total(upload) == 0 and files(upload) == []


def test_byte_row_column_and_cell_bounds(upload):
    settings = upload["settings"]
    settings.csv_max_bytes = 1024
    assert send(upload, b"source_id,notes\nx," + b"x" * 1100 + b"\n").status_code == 413
    settings.csv_max_bytes = 1048576
    settings.csv_max_rows = 1
    assert send(upload, b"source_id\nx\ny\n").status_code == 413
    settings.csv_max_rows = 2000
    settings.csv_max_columns = 30
    assert (
        send(
            upload,
            (
                ",".join("field" + str(n) for n in range(31))
                + "\n"
                + ",".join("0" for _ in range(31))
                + "\n"
            ).encode(),
        ).status_code
        == 413
    )
    settings.csv_max_field_bytes = 128
    assert send(upload, b"source_id,notes\nx," + b"x" * 129 + b"\n").status_code == 413
    assert total(upload) == 0 and files(upload) == []


def test_contract_reports_effective_staging_limits(upload):
    settings = upload["settings"]
    settings.csv_max_rows = 17
    settings.csv_max_bytes = 4096
    response = upload["client"].get(PATH + "/contract", headers=upload["auth"])
    assert response.status_code == 200
    assert response.json()["limits"] == {
        "max_bytes": 4096,
        "max_rows": 17,
        "max_columns": settings.csv_max_columns,
        "max_field_bytes": settings.csv_max_field_bytes,
    }


def test_chunked_upload_cannot_bypass_size_cap(upload):
    upload["settings"].csv_max_bytes = 1024
    response = send(upload, iter([b"source_id,notes\n", b"x," + b"y" * 800, b"z" * 800 + b"\n"]))
    assert response.status_code == 413 and files(upload) == [] and total(upload) == 0


def test_upload_above_old_json_limit_and_bom_formula_cells_are_data(upload, caplog):
    data = b"\xef\xbb\xbfsource_id,notes\n" + b"synthetic," + b"x" * 1000 + b"\n"
    data += b"synthetic," + b"=HYPERLINK(never-executed)" + b"\n"
    data += (b"synthetic," + b"y" * 1000 + b"\n") * 80
    response = send(upload, data)
    assert len(data) > 65536 and response.status_code == 201
    with upload["service"].open_for_validation(
        upload["actor_id"], UUID(response.json()["upload_id"])
    ) as reader:
        assert reader.read() == data
    assert "HYPERLINK" not in response.text and "HYPERLINK" not in caplog.text
    # This endpoint's stream exception does not raise limits on any existing JSON endpoint.
    assert (
        upload["client"]
        .post("/api/v1/alerts", content=b"x" * 70000, headers=upload["auth"])
        .status_code
        == 413
    )


def test_staging_does_not_validate_mapping_or_predictor_values(upload):
    response = send(upload, b"custom income,source label\nnot-a-number,private-marker\n")
    assert response.status_code == 201
    assert "private-marker" not in response.text


def test_same_key_replays_different_key_preserves_intent_and_conflicts_cleanup(upload):
    first = send(upload)
    replay = send(upload)
    assert first.status_code == 201 and replay.status_code == 200 and first.json() == replay.json()
    assert send(upload, sample(source="different-private-source")).status_code == 409
    assert send(upload, b"malformed-private-header\n").status_code == 409
    second = send(upload, key="different-upload-intent")
    assert second.status_code == 201 and second.json()["upload_id"] != first.json()["upload_id"]
    assert total(upload) == len(files(upload)) == 2


def test_capacity_does_not_reject_authorized_matching_retries(upload):
    upload["settings"].csv_max_active_uploads = 1
    assert send(upload).status_code == 201
    assert send(upload).status_code == 200
    limited = send(upload, key="new-distinct-upload-key")
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
    assert total(upload) == len(files(upload)) == 1


def test_inflight_capacity_rejects_before_creating_private_spools(upload):
    slots = upload["client"].app.state.csv_upload_slots
    for _ in range(upload["settings"].csv_max_concurrent_uploads):
        assert slots.acquire(blocking=False)
    try:
        response = send(upload)
        assert response.status_code == 429 and response.headers["retry-after"] == "5"
        assert total(upload) == 0 and files(upload) == []
    finally:
        for _ in range(upload["settings"].csv_max_concurrent_uploads):
            slots.release()
    assert send(upload).status_code == 201


def test_role_revocation_after_streaming_fails_publication_and_cleans_spool(upload, monkeypatch):
    original = IncomingCSV.append

    def revoke(incoming, chunk):
        original(incoming, chunk)
        if chunk:
            with Session(upload["engine"]) as session, session.begin():
                session.get(User, upload["actor_id"]).role = "analyst"

    monkeypatch.setattr(IncomingCSV, "append", revoke)
    assert send(upload).status_code == 403
    assert total(upload) == 0 and files(upload) == []


def test_role_revocation_blocks_metadata_and_internal_consumer(upload):
    result = send(upload).json()
    with Session(upload["engine"]) as session, session.begin():
        session.get(User, upload["actor_id"]).role = "analyst"
    assert (
        upload["client"].get(PATH + "/" + result["upload_id"], headers=upload["auth"]).status_code
        == 403
    )
    with (
        pytest.raises(UploadDenied),
        upload["service"].open_for_validation(upload["actor_id"], UUID(result["upload_id"])),
    ):
        pass


def test_post_promotion_file_failure_rolls_back_metadata_audit_and_bytes(upload, monkeypatch):
    original = IncomingCSV.promote

    def fail(incoming):
        original(incoming)
        raise OSError("private-path-marker")

    monkeypatch.setattr(IncomingCSV, "promote", fail)
    response = send(upload)
    assert response.status_code == 503 and "private" not in response.text
    assert total(upload) == 0 and files(upload) == []
    with Session(upload["engine"]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "batch.upload.staged")
            )
            == 0
        )


def test_private_consumer_rejects_tampering_and_missing_files(upload):
    result = send(upload).json()
    path = files(upload)[0]
    path.write_bytes(b"private-corrupt-marker")
    with (
        pytest.raises(StagingUnavailable),
        upload["service"].open_for_validation(upload["actor_id"], UUID(result["upload_id"])),
    ):
        pass
    path.unlink()
    with (
        pytest.raises(StagingUnavailable),
        upload["service"].open_for_validation(upload["actor_id"], UUID(result["upload_id"])),
    ):
        pass
    with (
        pytest.raises(UploadNotFound),
        upload["service"].open_for_validation(upload["actor_id"], uuid4()),
    ):
        pass
    if os.name != "nt":
        os.mkfifo(path)
        with (
            pytest.raises(StagingUnavailable),
            upload["service"].open_for_validation(upload["actor_id"], UUID(result["upload_id"])),
        ):
            pass


def test_expired_metadata_read_and_replay_remove_bytes_preserve_receipt(upload):
    result = send(upload).json()
    with Session(upload["engine"]) as session, session.begin():
        row = session.get(CSVUpload, UUID(result["upload_id"]))
        from datetime import timedelta

        row.created_at -= timedelta(days=2)
        row.expires_at -= timedelta(days=2)
    expired = upload["client"].get(PATH + "/" + result["upload_id"], headers=upload["auth"])
    assert expired.status_code == 200 and expired.json()["status"] == "expired"
    assert send(upload).status_code == 410
    assert send(upload, sample(source="different")).status_code == 409
    assert total(upload) == 1 and files(upload) == []
    with (
        pytest.raises(UploadExpired),
        upload["service"].open_for_validation(upload["actor_id"], UUID(result["upload_id"])),
    ):
        pass


def test_retention_orphans_and_active_spool_safety(upload):
    assert send(upload).status_code == 201
    old = upload["service"].begin()
    old.append(b"source_id\nx\n")
    active = upload["service"].begin()
    active.append(b"source_id\ny\n")
    old.file.flush()
    os.utime(old.path, (1, 1))
    unrelated = upload["settings"].csv_staging_root / "operator-note.txt"
    unrelated.write_text("synthetic-test-note")
    try:
        if os.name == "nt":
            old.file.close()  # Windows cannot unlink an open handle; real orphan has no owner.
        assert upload["service"].cleanup() == 1
        assert not old.path.exists() and active.path.exists() and unrelated.exists()
        assert len([p for p in files(upload) if p.suffix == ".csv"]) == 1
    finally:
        old.close()
        active.close()


def test_private_upload_has_no_public_byte_route_and_bad_reference_fails_closed(upload):
    result = send(upload).json()
    identifier = result["upload_id"]
    for path in [
        PATH + "/" + identifier + "/file",
        "/runtime/csv-staging/" + UUID(identifier).hex + ".csv",
    ]:
        response = upload["client"].get(path, headers=upload["auth"])
        assert response.status_code == 404 and "synthetic-csv" not in response.text
    with Session(upload["engine"]) as session, session.begin():
        session.get(CSVUpload, UUID(identifier)).storage_key = "../private.csv"
    with (
        pytest.raises(StagingUnavailable),
        upload["service"].open_for_validation(upload["actor_id"], UUID(identifier)),
    ):
        pass


def test_disconnect_cleans_private_partial_file(upload):
    import asyncio

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "headers": [
            (b"authorization", upload["auth"]["Authorization"].encode()),
            (b"content-type", b"text/csv"),
            (b"idempotency-key", KEY.encode()),
        ],
    }
    incoming = iter(
        [
            {
                "type": "http.request",
                "body": b"source_id,notes\nprivate-partial",
                "more_body": True,
            },
            {"type": "http.disconnect"},
        ]
    )
    statuses = []

    async def receive():
        return next(incoming, {"type": "http.disconnect"})

    async def send_message(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    asyncio.run(upload["client"].app(scope, receive, send_message))
    assert 408 in statuses and total(upload) == 0 and files(upload) == []


def test_orphan_reconciliation_cycles_past_the_first_page(upload):
    assert send(upload).status_code == 201
    for n in range(12):
        (upload["service"].root / f"operator-note-{n}.txt").write_text("synthetic")
    orphan = upload["service"].root / (uuid4().hex + ".csv")
    orphan.write_bytes(b"private-orphan")
    os.utime(orphan, (1, 1))
    removed = sum(upload["service"].cleanup(limit=3) for _ in range(8))
    assert removed == 1 and not orphan.exists()


def test_rejects_public_storage_configuration(upload):
    from app.core.config import PROJECT_ROOT

    copy = upload["settings"].model_copy(
        update={"csv_staging_root": PROJECT_ROOT / "frontend" / "public" / "uploads"}
    )
    with pytest.raises(StagingUnavailable):
        CSVStagingService(upload["engine"], copy)


@pytest.mark.postgres
def test_concurrent_requests_and_conflicts_on_real_postgres(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("Actual PostgreSQL row-lock concurrency")
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: send(upload), range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["upload_id"] for r in responses}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        conflicts = list(
            pool.map(
                lambda i: send(
                    upload, sample(source="race-" + str(i)), key="concurrent-conflicting-key"
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in conflicts) == [201, 409]
    assert total(upload) == len(files(upload)) == 2


@pytest.mark.postgres
def test_real_database_audit_failure_rolls_back_and_does_not_leak(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("Actual PostgreSQL audit trigger failure")
    with upload["engine"].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION reject_csv_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-csv-audit-marker'; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER reject_csv_audit BEFORE INSERT ON audit_events FOR EACH ROW WHEN (NEW.action='batch.upload.staged') EXECUTE FUNCTION reject_csv_audit()"
            )
        )
    response = send(upload)
    assert response.status_code == 503 and "private" not in response.text
    assert total(upload) == 0 and files(upload) == []


@pytest.mark.postgres
def test_unknown_commit_result_retains_published_bytes_for_idempotent_retry(upload, monkeypatch):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("Actual PostgreSQL commit acknowledgement fault")
    original = upload["engine"].dialect.do_commit
    armed = True

    def lost_ack(connection):
        nonlocal armed
        original(connection)
        if armed:
            armed = False
            raise SQLAlchemyError("private-commit-marker")

    monkeypatch.setattr(upload["engine"].dialect, "do_commit", lost_ack)
    response = send(upload)
    assert response.status_code == 503 and "private" not in response.text
    assert total(upload) == len(files(upload)) == 1
    retry = send(upload)
    assert retry.status_code == 200 and total(upload) == len(files(upload)) == 1


@pytest.mark.postgres
def test_rolled_back_commit_failure_is_reconciled_without_losing_receipts(upload, monkeypatch):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("Actual PostgreSQL failed commit")
    original = upload["engine"].dialect.do_commit

    def fail_commit(connection):
        raise SQLAlchemyError("private-commit-failed")

    monkeypatch.setattr(upload["engine"].dialect, "do_commit", fail_commit)
    assert send(upload).status_code == 503
    assert total(upload) == 0 and len(files(upload)) == 1
    monkeypatch.setattr(upload["engine"].dialect, "do_commit", original)
    os.utime(files(upload)[0], (1, 1))
    assert upload["service"].cleanup() == 1 and files(upload) == []
