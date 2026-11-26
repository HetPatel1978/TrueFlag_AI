"""Release boundaries: real isolated schema, no live migrations or model changes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session
from test_assessment_jobs import expire, result_for
from test_assessment_jobs import jobs as _jobs
from test_assessments import assessment_setup as _assessment_setup
from test_foundation import headers

from app.core import release, release_metadata
from app.core.release import release_report, require_compatible, require_session_compatible
from app.core.release_metadata import (
    ReleaseCompatibilityError,
    identity_digest,
    load_identity,
    unknown_identity,
)
from app.core.schema import EXPECTED_SCHEMA_REVISION
from app.models import Assessment, AssessmentJob, AuditEvent
from app.services.assessment_jobs import JobUnavailable, LeaseLost
from app.services.csv_imports import CSVImportService, ImportUnavailable
from app.services.evidence import EvidenceUnavailable
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.investigation_drafts import InvestigationDraftService

assessment_setup = _assessment_setup
jobs = _jobs


def revision(engine, value):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num=:revision"), {"revision": value}
        )


@pytest.fixture
def postgres_release(platform):
    if platform[1].dialect.name != "postgresql":
        pytest.skip("Requires isolated real PostgreSQL")
    return platform


@pytest.fixture
def release_jobs(postgres_release, jobs):
    return jobs


def job_snapshot(engine):
    with Session(engine) as session:
        return {
            "jobs": [
                (row.id, row.status, row.attempts, row.lease_token)
                for row in session.scalars(select(AssessmentJob))
            ],
            "assessments": session.scalar(select(func.count()).select_from(Assessment)),
            "audits": session.scalar(select(func.count()).select_from(AuditEvent)),
        }


def test_missing_metadata_is_explicit_unknown_without_inventing_git(tmp_path):
    result = load_identity(tmp_path / "absent.json")
    assert result["git_commit"] == result["build_id"] == result["image_digest"] == "unknown"
    assert result["metadata_status"] == "unknown"
    assert result["expected_schema_revision"] == EXPECTED_SCHEMA_REVISION


@pytest.mark.parametrize(
    "mutation",
    [
        "invalid_json",
        "extra",
        "wrong_schema",
        "wrong_worker",
        "bad_digest",
        "duplicate",
        "oversized",
    ],
)
def test_invalid_metadata_fails_closed_without_echoing_values(tmp_path, mutation):
    value = unknown_identity()
    if mutation == "extra":
        value["password"] = "private-credential-marker"
    elif mutation == "wrong_schema":
        value["expected_schema_revision"] = "0012_evidence_foundation"
    elif mutation == "wrong_worker":
        value["worker_version"] = "99.0.0"
    elif mutation == "bad_digest":
        value["build_id"] = "f" * 64
    raw = json.dumps(value)
    if mutation == "invalid_json":
        raw = "private-credential-marker"
    elif mutation == "duplicate":
        raw = raw[:-1] + ', "contract":"private-credential-marker"}'
    elif mutation == "oversized":
        raw = " " * 8193
    path = tmp_path / "release.json"
    path.write_text(raw)
    with pytest.raises(ReleaseCompatibilityError) as error:
        load_identity(path)
    assert "private-credential-marker" not in str(error.value)


def test_valid_build_identity_and_version_sources(tmp_path):
    value = {
        **unknown_identity(),
        "git_commit": "a" * 40,
        "source_state": "dirty",
        "source_sha256": "b" * 64,
    }
    value["build_id"] = identity_digest(value)
    path = tmp_path / "release.json"
    path.write_text(json.dumps(value))
    assert load_identity(path)["git_commit"] == "a" * 40
    import tomllib

    root = Path(__file__).resolve().parents[2]
    backend = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]["version"]
    frontend_file = root / "frontend/package.json"
    frontend = (
        json.loads(frontend_file.read_text())["version"]
        if frontend_file.is_file()
        else value["frontend_version"]
    )
    assert backend == value["backend_version"] == value["worker_version"]
    assert frontend == value["frontend_version"]


def test_health_and_ready_contracts_and_protected_details(platform):
    client, _, _, _ = platform
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "trueflag-ai",
        "version": "0.1.0",
    }
    ready = client.get("/ready")
    assert ready.json() == {"status": "ready"} and ready.status_code == 200
    assert ready.headers["x-readiness-code"] == "compatible"
    path = "/api/v1/internal/release"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(platform, "analyst")).status_code == 403
    report = client.get(path, headers=headers(platform)).json()
    assert report["schema"] == {
        "expected": EXPECTED_SCHEMA_REVISION,
        "actual": EXPECTED_SCHEMA_REVISION,
    }
    assert report["ml"]["verification"] == "not_checked_in_api_process"
    assert "database_url" not in json.dumps(report) and "jwt_secret" not in json.dumps(report)


def test_missing_build_file_keeps_known_contract_but_unknown_provenance(
    platform, tmp_path, monkeypatch
):
    monkeypatch.setattr(release_metadata, "METADATA_PATH", tmp_path / "absent.json")
    assert platform[0].get("/ready").json() == {"status": "ready"}
    identity = release_report(platform[1])["release"]
    assert identity["contract"] == "trueflag.release.v1"
    assert identity["build_id"] == identity["git_commit"] == "unknown"


def test_incompatible_python_is_rejected(platform, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(release, "sys", SimpleNamespace(version_info=(3, 12)))
    with pytest.raises(ReleaseCompatibilityError, match="^python_incompatible$"):
        require_compatible(platform[1])


@pytest.mark.postgres
def test_readiness_schema_lock_is_bounded_and_recovers(postgres_release):
    engine = postgres_release[1]
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
        report = release_report(engine)
        assert report["status"] == "not_ready" and report["compatibility"] == "schema_unavailable"
        assert report["dependencies"]["database"] == "available"
    assert release_report(engine)["status"] == "ready"


@pytest.mark.postgres
def test_revision_is_fenced_through_short_worker_transaction(postgres_release):
    engine = postgres_release[1]
    with Session(engine) as guarded, guarded.begin():
        require_session_compatible(guarded)
        with pytest.raises(DBAPIError) as error:
            with engine.begin() as competing:
                competing.execute(text("SET LOCAL lock_timeout='100ms'"))
                competing.execute(
                    text("UPDATE alembic_version SET version_num='0012_evidence_foundation'")
                )
        assert error.value.orig.sqlstate == "55P03"
    revision(engine, "0012_evidence_foundation")
    with pytest.raises(ReleaseCompatibilityError, match="^schema_incompatible$"):
        require_compatible(engine)


@pytest.mark.parametrize("state", ["older", "multiple", "missing"])
def test_mismatched_or_missing_schema_is_not_ready_and_blocks_business_requests(platform, state):
    client, engine, _, _ = platform
    auth = headers(platform)
    with engine.begin() as connection:
        if state == "older":
            connection.execute(
                text("UPDATE alembic_version SET version_num='0012_evidence_foundation'")
            )
        elif state == "multiple":
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('0012_evidence_foundation')"
                )
            )
        else:
            connection.execute(text("DROP TABLE alembic_version"))
    ready = client.get("/ready")
    assert ready.status_code == 503 and ready.json() == {"status": "not_ready"}
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/cases", headers=auth).status_code == 503
    detail = client.get("/api/v1/internal/release", headers=auth).json()
    assert detail["dependencies"]["database"] == "available"
    assert detail["status"] == "not_ready"
    assert "expected" not in ready.json()  # Infrastructure details remain admin-only.


def test_malformed_runtime_metadata_blocks_api_and_is_sanitized(platform, tmp_path, monkeypatch):
    client, engine, _, _ = platform
    auth = headers(platform)
    path = tmp_path / "bad.json"
    path.write_text('"private-credential-marker"')
    monkeypatch.setattr(release_metadata, "METADATA_PATH", path)
    ready = client.get("/ready")
    assert (
        ready.status_code == 503 and ready.headers["x-readiness-code"] == "release_metadata_invalid"
    )
    assert client.get("/api/v1/cases", headers=auth).status_code == 503
    report = release_report(engine)
    assert report["release"]["metadata_status"] == "invalid"
    assert "private-credential-marker" not in json.dumps(report)


def test_database_unavailable_is_distinct_and_does_not_leak_errors(platform, monkeypatch):
    client, engine, _, _ = platform

    def unavailable(*args, **kwargs):
        raise OperationalError(
            "private-connection-marker", {}, Exception("private-credential-marker")
        )

    monkeypatch.setattr(engine, "connect", unavailable)
    ready = client.get("/ready")
    assert ready.status_code == 503 and ready.headers["x-readiness-code"] == "database_unavailable"
    assert client.get("/health").status_code == 200
    report = release_report(engine)
    assert report["dependencies"]["database"] == "unavailable"
    assert "private-" not in json.dumps(report)


@pytest.mark.postgres
def test_incompatible_assessment_worker_cannot_claim_or_publish_and_recovers(
    platform, release_jobs
):
    queue, token, request, producer, _ = release_jobs
    engine = platform[1]
    job, _ = queue.enqueue(**request)
    baseline = job_snapshot(engine)
    revision(engine, "0012_evidence_foundation")
    for call in [lambda: queue.claim(token), lambda: queue.recover_expired(token)]:
        with pytest.raises(JobUnavailable, match="^schema_incompatible$"):
            call()
    assert job_snapshot(engine) == baseline
    revision(engine, EXPECTED_SCHEMA_REVISION)
    claim = queue.claim(token)
    result = result_for(queue, token, claim, producer)
    baseline = job_snapshot(engine)
    revision(engine, "0012_evidence_foundation")
    for call in [
        lambda: queue.prepare(token, claim),
        lambda: queue.complete(token, claim, result),
        lambda: queue.heartbeat(token, claim),
        lambda: queue.fail(token, claim, "database_unavailable"),
    ]:
        with pytest.raises(JobUnavailable, match="^schema_incompatible$"):
            call()
    assert job_snapshot(engine) == baseline
    expire(engine)
    revision(engine, EXPECTED_SCHEMA_REVISION)
    assert queue.recover_expired(token) == 1
    from test_assessment_jobs import due

    due(engine)
    renewed = queue.claim(token)
    with pytest.raises(LeaseLost):
        queue.complete(token, claim, result)
    queue.complete(token, renewed, result_for(queue, token, renewed, producer))
    assert queue.enqueue(**request)[0]["status"] == "succeeded"
    assert job_snapshot(engine)["assessments"] == 1
    assert queue.claim(token) is None and job["job_id"]


@pytest.mark.postgres
def test_import_and_investigation_boundaries_reject_before_job_mutation(postgres_release):
    _, engine, settings, _ = postgres_release
    settings.investigation_simulation_enabled = (
        True  # Isolated fake-only service, no provider execution.
    )
    imported = CSVImportService(engine, settings)
    coordinator = InvestigationCoordinator(engine, settings)
    draft = InvestigationDraftService(engine, settings)
    revision(engine, "0012_evidence_foundation")
    for call, error in [
        (lambda: imported.claim("x" * 32), ImportUnavailable),
        (lambda: imported.recover_expired("x" * 32), ImportUnavailable),
        (lambda: coordinator.claim("x" * 32), EvidenceUnavailable),
        (lambda: coordinator.recover("x" * 32), EvidenceUnavailable),
        (lambda: draft.claim("x" * 32), EvidenceUnavailable),
        (lambda: draft.recover("x" * 32), EvidenceUnavailable),
    ]:
        with pytest.raises(error, match="^schema_incompatible$"):
            call()


@pytest.mark.postgres
@pytest.mark.parametrize(
    "module,flags",
    [
        ("assessment_worker", ["--once"]),
        ("csv_import_worker", ["--once"]),
        ("investigation_worker", ["--max-jobs", "1"]),
        ("investigation_draft_worker", ["--max-jobs", "1"]),
    ],
)
def test_real_linux_worker_startup_rejects_schema_without_claims(
    platform, release_jobs, tmp_path, module, flags
):
    if sys.platform != "linux":
        pytest.skip("Requires actual Linux worker process")
    queue, token, request, _, _ = release_jobs
    queue.enqueue(**request)
    baseline = job_snapshot(platform[1])
    token_path = tmp_path / "worker-token"
    token_path.write_text(token)
    revision(platform[1], "0012_evidence_foundation")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "app.workers." + module,
            "--token-file",
            str(token_path),
            *flags,
        ],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1
    value = json.loads(result.stdout)
    assert value["code"] == "schema_incompatible"
    assert token not in result.stdout + result.stderr
    assert job_snapshot(platform[1]) == baseline


def test_metadata_mismatch_rejects_worker_boundary(
    postgres_release, release_jobs, tmp_path, monkeypatch
):
    queue, token, request, _, _ = release_jobs
    queue.enqueue(**request)
    before = job_snapshot(postgres_release[1])
    value = unknown_identity()
    value["worker_version"] = "99.0.0"
    path = tmp_path / "other-worker.json"
    path.write_text(json.dumps(value))
    monkeypatch.setattr(release_metadata, "METADATA_PATH", path)
    with pytest.raises(JobUnavailable, match="^release_contract_incompatible$"):
        queue.claim(token)
    with pytest.raises(ReleaseCompatibilityError, match="^release_contract_incompatible$"):
        require_compatible(postgres_release[1])
    assert job_snapshot(postgres_release[1]) == before


@pytest.mark.postgres
def test_actual_linux_ml_worker_preflight_and_idle_preserve_jobs(platform, release_jobs, tmp_path):
    if sys.platform != "linux" or os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1":
        pytest.skip("Requires actual pinned Linux ML artifacts and runtime")
    _, token, _, _, _ = release_jobs
    path = tmp_path / "worker-token"
    path.write_text(token)
    before = job_snapshot(platform[1])
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "app.workers.assessment_worker",
            "--token-file",
            str(path),
            "--once",
        ],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "idle"
    assert (
        output["release"]["ml_verification"] == "sha256_and_dependencies_verified_not_deserialized"
    )
    assert token not in result.stdout + result.stderr
    assert job_snapshot(platform[1]) == before
