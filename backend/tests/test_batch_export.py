"""Server-enforced export scope, CSV safety, allowlist, bounded range and audit atomicity."""

import csv
import hashlib
import io
import os
import sys

import pytest
import test_batch_assessments
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_batch_assessments import advance, fail_all, imported, start
from test_foundation import headers

from app.models import AuditEvent, User
from app.services.batch_export import EXPORT_FIELDS, safe_cell

base_upload = test_batch_assessments.base_upload
import_fixture = test_batch_assessments.import_fixture
batch_env = test_batch_assessments.batch_env


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+SUM(A1)",
        "-1+2",
        "@cmd",
        " \t=cmd",
        "\ttext",
        "\rtext",
        "\ntext",
        "\ufeff=cmd",
        " \ufeff@cmd",
    ],
)
def test_spreadsheet_formula_prefixes_are_neutralized(value):
    assert safe_cell(value) == "'" + value


def test_safe_numeric_and_identifier_values_preserved():
    assert (
        safe_cell(0.125) == "0.125"
        and safe_cell(None) == ""
        and safe_cell("ordinary-id") == "ordinary-id"
    )


def ready(env):
    first = start(env, imported(env, [{}, {}, {}]))
    advance(env, first.json()["batch_id"])
    fail_all(env)
    advance(env, first.json()["batch_id"])
    fail_all(env)
    return first.headers["location"], first.json()["batch_id"]


def test_export_allowlist_range_filenames_hash_audit_and_no_features(batch_env, caplog):
    env = batch_env
    path, bid = ready(env)
    response = env["client"].get(path + "/export?offset=1&limit=1", headers=env["auth"])
    assert response.status_code == 200
    assert (
        response.headers["cache-control"] == "no-store"
        and response.headers["x-export-total"] == "3"
    )
    assert (
        response.headers["x-export-rows"] == "1"
        and "attachment;" in response.headers["content-disposition"]
    )
    assert bid in response.headers["content-disposition"] and response.content.startswith(
        b"\xef\xbb\xbf"
    )
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))
    assert (
        len(rows) == 1 and tuple(rows[0]) == EXPORT_FIELDS and rows[0]["source_row_number"] == "3"
    )
    assert rows[0]["outcome"] == "failed_manual_review" and rows[0]["sar_positive_score"] == ""
    assert rows[0]["human_decision_required"] == "True"
    for private in ("income", "source_id", "raw_features", "storage_key", "worker_token"):
        assert private not in rows[0]
    with Session(env["engine"]) as session:
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "batch.assessment.exported")
        )
        assert (
            audit.details["sha256"] == hashlib.sha256(response.content).hexdigest()
            and audit.details["returned"] == 1
        )
    assert "preview-synthetic-" not in response.text + caplog.text


def test_export_current_owner_role_and_case_authorization(batch_env, platform, monkeypatch):
    from sqlalchemy import false

    import app.services.batch_assessments as module

    env = batch_env
    path, _ = ready(env)
    assert env["client"].get(path + "/export").status_code == 401
    assert (
        env["client"].get(path + "/export", headers=headers(platform, "analyst")).status_code == 403
    )
    with Session(env["engine"]) as session, session.begin():
        owner = session.get(User, env["actor_id"])
        session.add(
            User(username="exportotheradmin", role="admin", password_hash=owner.password_hash)
        )
    assert (
        env["client"]
        .get(path + "/export", headers=headers(platform, "exportotheradmin"))
        .status_code
        == 404
    )
    with monkeypatch.context() as patch:
        patch.setattr(module, "visible_cases", lambda user: false())
        assert env["client"].get(path + "/export", headers=env["auth"]).status_code == 404
    with Session(env["engine"]) as session, session.begin():
        session.get(User, env["actor_id"]).role = "supervisor"
    assert env["client"].get(path + "/export", headers=env["auth"]).status_code == 403


def test_export_limits_no_truncation_and_field_selection_rejected(batch_env):
    env = batch_env
    path, _ = ready(env)
    env["settings"].batch_export_max_rows = 1
    assert env["client"].get(path + "/export?limit=2", headers=env["auth"]).status_code == 413
    assert (
        env["client"].get(path + "/export?limit=1&fields=income", headers=env["auth"]).status_code
        == 422
    )
    assert env["client"].get(path + "/export?limit=1001", headers=env["auth"]).status_code == 422
    env["settings"].batch_export_max_rows = 500
    env["settings"].batch_export_max_bytes = 1024
    response = env["client"].get(path + "/export?limit=3", headers=env["auth"])
    assert response.status_code == 413 and "case_id" not in response.text
    with Session(env["engine"]) as session:
        assert (
            session.scalar(
                select(AuditEvent.id).where(AuditEvent.action == "batch.assessment.exported")
            )
            is None
        )


def test_export_audit_failure_releases_no_csv(batch_env):
    env = batch_env
    path, _ = ready(env)
    with env["engine"].begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION fail_export_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='batch.assessment.exported' THEN RAISE EXCEPTION 'private-export-details'; END IF; RETURN NEW; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER fail_export_audit BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION fail_export_audit()"
            )
        )
    response = env["client"].get(path + "/export?limit=1", headers=env["auth"])
    assert (
        response.status_code == 503
        and "private-export-details" not in response.text
        and "case_id" not in response.text
    )


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1" or sys.platform != "linux",
    reason="actual pinned Linux score/SHAP",
)
def test_actual_verified_result_export_matches_api(batch_env):
    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    first = start(env, imported(env, [{}]))
    advance(env, first.json()["batch_id"])
    assert AssessmentWorker(env["ml"], env["ml_token"]).run_once()["status"] == "succeeded"
    detail = (
        env["client"]
        .get(first.headers["location"] + "/results", headers=env["auth"])
        .json()["items"][0]["assessment"]
    )
    response = env["client"].get(first.headers["location"] + "/export?limit=1", headers=env["auth"])
    assert response.status_code == 200
    row = next(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert (
        float(row["sar_positive_score"]) == detail["score"]
        and row["recommendation"] == detail["recommended_route"]
    )
    assert (
        row["model_sha256"] == detail["model_sha256"]
        and row["assessment_id"] == detail["assessment_id"]
    )
