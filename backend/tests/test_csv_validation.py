"""Synthetic-only contract, privacy, streaming and real PostgreSQL preview acceptance."""

import csv
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import test_csv_staging
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_csv_staging import PATH, sample, send
from test_foundation import headers

from app.models import (
    Alert,
    AssessmentJob,
    AuditEvent,
    Case,
    CSVUpload,
    CSVValidation,
    CSVValidationIssue,
    User,
)
from app.schemas.alerts import AlertIngestionInput
from app.schemas.csv_uploads import COLUMNS
from app.schemas.csv_validation import MappingInput
from app.services.csv_staging import UploadDenied
from app.services.csv_validation import CSVValidationService

staging_upload = test_csv_staging.upload


@pytest.fixture
def upload(staging_upload):
    return staging_upload


def data(rows, names=COLUMNS):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(names)
    for i, changes in enumerate(rows):
        row = {n: "0" for n in COLUMNS}
        row.update(
            source_id=f"preview-synthetic-{i}",
            data_classification="synthetic",
            feature_contract_version="datarobot_provisional_v1",
            state="QZ",
            kycRiskScore="3",
            income="",
        )
        row.update(changes)
        writer.writerow(
            [row[n] for n in COLUMNS] + ["inert" for _ in range(len(names) - len(COLUMNS))]
        )
    return output.getvalue().encode()


def staged(upload, body=None):
    response = send(
        upload, sample() if body is None else body, key="preview-staging-" + uuid4().hex
    )
    assert response.status_code == 201, response.text
    return response.json()["upload_id"]


def validate(upload, upload_id, body=None, auth=None):
    return upload["client"].post(
        PATH + f"/{upload_id}/validations",
        json={"units": "baseline_source_units"} if body is None else body,
        headers=upload["auth"] if auth is None else auth,
    )


def diagnostics(upload, upload_id, result, query=""):
    return upload["client"].get(
        PATH + f"/{upload_id}/validations/{result['validation_id']}/errors" + query,
        headers=upload["auth"],
    )


def count(upload, model):
    with Session(upload["engine"]) as session:
        return session.scalar(select(func.count()).select_from(model))


def test_exact_mapping_versions_safe_summary_digest_no_import(upload, caplog):
    body = data([{}, {"income": "0"}])
    uid = staged(upload, body)
    columns = upload["client"].get(PATH + f"/{uid}/columns", headers=upload["auth"])
    assert columns.status_code == 200 and columns.json()["columns"] == list(COLUMNS)
    response = validate(upload, uid)
    assert response.status_code == 201, response.text
    result = response.json()
    assert (
        result["total_rows"],
        result["valid_rows"],
        result["invalid_rows"],
        result["warning_rows"],
    ) == (2, 2, 0, 0)
    assert result["upload_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["mapping"] == {n: n for n in COLUMNS} and result["version"] == 1
    assert response.headers["cache-control"] == "no-store"
    same = validate(
        upload,
        uid,
        {
            "units": "baseline_source_units",
            "mapping": dict(reversed(list(result["mapping"].items()))),
        },
    )
    assert same.status_code == 200 and same.json()["validation_id"] == result["validation_id"]
    summary = upload["client"].get(response.headers["location"], headers=upload["auth"])
    assert summary.json() == result
    assert diagnostics(upload, uid, result).json()["items"] == []
    for model in (Alert, Case, AssessmentJob):
        assert count(upload, model) == 0
    with Session(upload["engine"]) as session:
        row = session.get(CSVUpload, UUID(uid))
        assert (upload["settings"].csv_staging_root / row.storage_key).read_bytes() == body
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "batch.validation.completed")
        )
        assert audit.details["valid_rows"] == 2
        assert "mapping" not in audit.details
    assert "preview-synthetic-" not in response.text + summary.text + caplog.text


def test_alias_mapping_and_new_version_preserve_history(upload):
    names = tuple("column" + str(i) for i in range(30)) + ("alternative",)
    uid = staged(upload, data([{}], names))
    mapping = dict(zip(COLUMNS, names[:30], strict=True))
    assert validate(upload, uid).status_code == 422
    first = validate(upload, uid, {"units": "baseline_source_units", "mapping": mapping})
    assert first.status_code == 201 and first.json()["valid_rows"] == 1
    mapping["state"] = "alternative"
    second = validate(upload, uid, {"units": "baseline_source_units", "mapping": mapping})
    assert second.status_code == 201 and second.json()["version"] == 2
    assert first.json()["validation_id"] != second.json()["validation_id"]
    assert count(upload, CSVValidation) == 2


@pytest.mark.parametrize(
    "change", ["missing", "unknown", "duplicate", "absent", "case", "units", "version", "extra"]
)
def test_invalid_mapping_contract_rejected_without_writes(upload, change):
    uid = staged(upload)
    mapping = {n: n for n in COLUMNS}
    request = {"units": "baseline_source_units", "mapping": mapping}
    if change == "missing":
        mapping.pop("income")
    if change == "unknown":
        mapping["SAR"] = mapping.pop("income")
    if change == "duplicate":
        mapping["income"] = "state"
    if change == "absent":
        mapping["income"] = "Annual Income"
    if change == "case":
        mapping["state"] = "State"
    if change == "units":
        request["units"] = "USD_cents"
    if change == "version":
        request["mapping_version"] = "untrusted-version"
    if change == "extra":
        request["path"] = "C:/secret/private.csv"
    response = validate(upload, uid, request)
    assert response.status_code == 422
    assert "private.csv" not in response.text
    assert count(upload, CSVValidation) == 0


@pytest.mark.parametrize(
    "value",
    [
        "NaN",
        "Infinity",
        "true",
        "NULL",
        "null",
        "N/A",
        " ",
        "01",
        "+2",
        "1,000",
        "$1",
        "1e309",
        "1e-999",
        "1e-999999999999999999999999999999999999",
        "0 " * 100,
        "9" * 513,
    ],
)
def test_numeric_tokens_invalid_report_field_without_value(upload, value):
    uid = staged(upload, data([{"income": value}]))
    response = validate(upload, uid)
    assert response.status_code == 201 and response.json()["invalid_rows"] == 1
    page = diagnostics(upload, uid, response.json()).json()
    assert page["items"] == [
        {
            "row_number": 2,
            "errors": [{"field": "income", "code": "number_format"}],
            "warnings": (
                [{"field": "income", "code": "spreadsheet_formula"}]
                if value.startswith("+")
                else []
            ),
        }
    ]


def test_missing_zero_numeric_semantics_use_original_validator(upload, monkeypatch):
    original = AlertIngestionInput.model_validate
    observed = []

    def capture(value):
        observed.append(value["features"]["income"])
        return original(value)

    monkeypatch.setattr(AlertIngestionInput, "model_validate", capture)
    uid = staged(
        upload,
        data(
            [
                {},
                {"income": "0"},
                {"income": "-0.0"},
                {
                    "income": "2.5e2",
                    "PEP": "2",
                    "state": "unknown Category",
                    "nbrPurchases90d": "-1.5",
                },
            ]
        ),
    )
    result = validate(upload, uid)
    assert result.status_code == 201 and result.json()["valid_rows"] == 4
    assert observed == [None, 0, -0.0, 250.0]


def test_full_file_errors_numbering_pagination_and_inert_warnings(upload, caplog):
    rows = [
        {},
        {"income": "private-invalid-income"},
        {"kycRiskScore": "6.1", "data_classification": "private"},
        {"state": '=HYPERLINK("private")'},
        {"source_id": "preview-synthetic-0"},
    ]
    uid = staged(upload, data(rows))
    result = validate(upload, uid).json()
    assert (
        result["total_rows"],
        result["valid_rows"],
        result["invalid_rows"],
        result["warning_rows"],
    ) == (5, 2, 3, 1)
    first = diagnostics(upload, uid, result, "?offset=0&limit=2").json()
    second = diagnostics(upload, uid, result, "?offset=2&limit=2").json()
    assert first["total"] == 4 and [r["row_number"] for r in first["items"]] == [3, 4]
    assert [r["row_number"] for r in second["items"]] == [5, 6]
    assert second["items"][0]["warnings"] == [{"field": "state", "code": "spreadsheet_formula"}]
    assert second["items"][1]["errors"] == [{"field": "source_id", "code": "duplicate_source_id"}]
    assert diagnostics(upload, uid, result, "?severity=error").json()["total"] == 3
    assert diagnostics(upload, uid, result, "?severity=warning").json()["total"] == 1
    for query in ("?limit=101", "?offset=-1", "?offset=10001", "?severity=unsafe"):
        assert diagnostics(upload, uid, result, query).status_code == 422
    assert "private" not in str(first) + str(second) + caplog.text


def test_multiline_logical_row_numbers_and_width_errors(upload):
    uid = staged(upload, data([{"state": "unseen\ncategory"}, {"income": "bad"}, {}]) + b"\r\n")
    result = validate(upload, uid).json()
    assert result["total_rows"] == 4 and result["invalid_rows"] == 2
    page = diagnostics(upload, uid, result).json()
    assert [r["row_number"] for r in page["items"]] == [3, 5]
    assert page["items"][-1]["errors"] == [{"field": "row", "code": "column_count"}]


def test_large_full_file_bounded_batches_and_limits(upload):
    uid = staged(upload, data([{"income": "bad"} for _ in range(2000)]))
    result = validate(upload, uid)
    assert result.status_code == 201 and result.json()["invalid_rows"] == 2000
    assert count(upload, CSVValidationIssue) == 2000
    last = diagnostics(upload, uid, result.json(), "?offset=1999&limit=100").json()
    assert last["items"][0]["row_number"] == 2001 and len(last["items"]) == 1


def test_permissions_owner_scope_revocation_and_expiry(upload, platform):
    uid = staged(upload)
    result = validate(upload, uid).json()
    suffixes = [
        "/columns",
        "/validations/" + result["validation_id"],
        "/validations/" + result["validation_id"] + "/errors",
    ]
    for suffix in suffixes:
        assert upload["client"].get(PATH + f"/{uid}" + suffix).status_code == 401
        assert (
            upload["client"]
            .get(PATH + f"/{uid}" + suffix, headers=headers(platform, "analyst"))
            .status_code
            == 403
        )
    assert validate(upload, uid, auth={}).status_code == 401
    assert validate(upload, uid, auth=headers(platform, "analyst")).status_code == 403
    with Session(upload["engine"]) as session, session.begin():
        owner = session.get(User, upload["actor_id"])
        other = User(username="previewadmin", role="admin", password_hash=owner.password_hash)
        session.add(other)
    other_auth = headers(platform, "previewadmin")
    for suffix in suffixes:
        assert (
            upload["client"].get(PATH + f"/{uid}" + suffix, headers=other_auth).status_code == 404
        )
    assert validate(upload, uid, auth=other_auth).status_code == 404
    with Session(upload["engine"]) as session, session.begin():
        session.get(User, upload["actor_id"]).role = "analyst"
    assert validate(upload, uid).status_code == 403
    for suffix in suffixes:
        assert (
            upload["client"].get(PATH + f"/{uid}" + suffix, headers=upload["auth"]).status_code
            == 403
        )
    with Session(upload["engine"]) as session, session.begin():
        session.get(User, upload["actor_id"]).role = "admin"
        row = session.get(CSVUpload, UUID(uid))
        row.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert validate(upload, uid).status_code == 410
    assert diagnostics(upload, uid, result).status_code == 410


def test_recheck_role_between_api_dependency_and_processing(upload, monkeypatch):
    import app.api.csv_uploads as routes

    factory = routes.validation_service
    uid = staged(upload)

    def revoke(request):
        with Session(upload["engine"]) as session, session.begin():
            session.get(User, upload["actor_id"]).role = "analyst"
        return factory(request)

    monkeypatch.setattr(routes, "validation_service", revoke)
    assert validate(upload, uid).status_code == 403
    assert count(upload, CSVValidation) == 0
    with pytest.raises(UploadDenied):
        CSVValidationService(upload["engine"], upload["settings"]).validate(
            upload["actor_id"], UUID(uid), MappingInput(units="baseline_source_units")
        )


def test_capacity_timeout_and_quota_do_not_leave_partial_preview(upload, monkeypatch):
    import app.services.csv_validation as module

    uid = staged(upload)
    slots = upload["client"].app.state.csv_validation_slots
    for _ in range(upload["settings"].csv_max_concurrent_validations):
        assert slots.acquire(False)
    try:
        response = validate(upload, uid)
        assert response.status_code == 429 and response.headers["retry-after"] == "5"
    finally:
        for _ in range(upload["settings"].csv_max_concurrent_validations):
            slots.release()
    clock = iter([0, 100])
    with monkeypatch.context() as patch:
        patch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(clock)))
        assert validate(upload, uid).status_code == 503
    assert count(upload, CSVValidation) == count(upload, CSVValidationIssue) == 0
    assert validate(upload, uid).status_code == 201


def test_tampered_missing_bytes_cross_upload_and_request_limits(upload):
    uid = staged(upload)
    result = validate(upload, uid).json()
    other = staged(upload)
    assert diagnostics(upload, other, result).status_code == 404
    response = upload["client"].post(
        PATH + f"/{uid}/validations",
        content=b"x" * 65537,
        headers={**upload["auth"], "content-type": "application/json"},
    )
    assert response.status_code == 413
    duplicate = upload["client"].post(
        PATH + f"/{uid}/validations",
        content=b'{"units":"baseline_source_units","units":"baseline_source_units"}',
        headers={**upload["auth"], "content-type": "application/json"},
    )
    assert duplicate.status_code == 422
    assert (
        upload["client"]
        .post(
            PATH + f"/{uid}/validations",
            content=b"{}",
            headers={**upload["auth"], "content-type": "text/plain"},
        )
        .status_code
        == 415
    )
    with Session(upload["engine"]) as session:
        row = session.get(CSVUpload, UUID(uid))
        path = upload["settings"].csv_staging_root / row.storage_key
    path.write_bytes(b"bad,bytes\nsecret,record\n")
    assert validate(upload, uid).status_code == 503
    assert diagnostics(upload, uid, result).status_code == 503
    path.unlink()
    assert validate(upload, uid).status_code == 503


def test_mapping_version_quota_replay_allowed(upload):
    names = tuple(COLUMNS) + ("OtherState",)
    uid = staged(upload, data([{}], names))
    upload["settings"].csv_max_validation_versions = 1
    first = validate(upload, uid)
    assert first.status_code == 201
    mapping = {n: n for n in COLUMNS}
    mapping["state"] = "OtherState"
    assert (
        validate(upload, uid, {"units": "baseline_source_units", "mapping": mapping}).status_code
        == 429
    )
    assert validate(upload, uid).status_code == 200


def test_postgres_concurrent_identical_validation_single_version(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL serialization acceptance")
    uid = staged(upload)
    upload["client"].app.state.csv_validation_slots = BoundedSemaphore(4)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: validate(upload, uid), range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["validation_id"] for r in responses}) == 1
    assert count(upload, CSVValidation) == 1


def test_postgres_issue_failure_rolls_back_mapping_results_and_audit(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger rollback acceptance")
    uid = staged(upload, data([{"income": "bad"}]))
    with upload["engine"].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION fail_preview() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private_failure'; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER fail_preview BEFORE INSERT ON csv_validation_issues FOR EACH ROW EXECUTE FUNCTION fail_preview()"
            )
        )
    response = validate(upload, uid)
    assert response.status_code == 503 and "private_failure" not in response.text
    assert count(upload, CSVValidation) == count(upload, CSVValidationIssue) == 0
    with Session(upload["engine"]) as session:
        assert not session.scalars(
            select(AuditEvent).where(AuditEvent.action == "batch.validation.completed")
        ).all()


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_classification", "customer"),
        ("feature_contract_version", "other"),
        ("source_id", "=command"),
        ("state", " "),
        ("kycRiskScore", "7"),
        ("kycRiskScore", "-1"),
        ("kycRiskScore", "3.1"),
        ("tenureMonths", ""),
    ],
)
def test_canonical_metadata_and_predictor_failures(upload, field, value):
    uid = staged(upload, data([{field: value}]))
    result = validate(upload, uid).json()
    assert result["invalid_rows"] == 1
    errors = diagnostics(upload, uid, result).json()["items"][0]["errors"]
    assert len(errors) == 1 and errors[0]["field"] == field


def test_partial_writes_timeout_rollback_and_file_unchanged(upload, monkeypatch):
    import app.services.csv_validation as module

    body = data([{"income": "bad"} for _ in range(120)])
    uid = staged(upload, body)
    original = module.validate_row
    calls = 0

    def fail_late(*args):
        nonlocal calls
        calls += 1
        if calls == 110:
            raise module.StagingUnavailable
        return original(*args)

    with monkeypatch.context() as patch:
        patch.setattr(module, "validate_row", fail_late)
        assert validate(upload, uid).status_code == 503
    assert count(upload, CSVValidation) == count(upload, CSVValidationIssue) == 0
    assert validate(upload, uid).json()["invalid_rows"] == 120


def test_malformed_csv_and_changed_limits_fail_safely(upload):
    uid = staged(upload)
    # Inject storage corruption plus a forged test receipt to exercise strict parsing itself,
    # independently of the separately tested trusted-digest rejection.
    body = (",".join(COLUMNS) + '\r\n"unterminated').encode()
    with Session(upload["engine"]) as session, session.begin():
        receipt = session.get(CSVUpload, UUID(uid))
        (upload["settings"].csv_staging_root / receipt.storage_key).write_bytes(body)
        receipt.sha256 = hashlib.sha256(body).hexdigest()
        receipt.size_bytes = len(body)
    # Complete mapping succeeds; malformed quoted row must roll back the preview.
    assert validate(upload, uid).status_code == 422
    uid = staged(upload, data([{}, {}]))
    upload["settings"].csv_max_rows = 1
    assert validate(upload, uid).status_code == 413
    assert count(upload, CSVValidation) == 0


def test_postgres_concurrent_different_mappings_version_history(upload):
    if upload["engine"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL version serialization acceptance")
    uid = staged(upload, data([{}], tuple(COLUMNS) + ("OtherState",)))
    mapping = {n: n for n in COLUMNS}
    mapping["state"] = "OtherState"
    requests = [
        {"units": "baseline_source_units"},
        {"units": "baseline_source_units", "mapping": mapping},
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda request: validate(upload, uid, request), requests))
    assert [r.status_code for r in responses] == [201, 201]
    assert {r.json()["version"] for r in responses} == {1, 2}
    assert count(upload, CSVValidation) == 2
