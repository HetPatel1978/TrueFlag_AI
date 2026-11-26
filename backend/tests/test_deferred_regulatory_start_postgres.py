"""Native-runner acceptance targets. Synthetic fixtures are not official approvals."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_foundation import headers
from test_references import reference_env as reference_fixture

from alembic import command
from app.models.investigation_drafts import DraftAttempt, DraftRun, StoredDraft
from app.models.regulatory_drafts import DraftRegulatoryBinding
from app.schemas.draft_api import DraftStartInput
from app.schemas.investigations import InvestigationRequest
from app.schemas.references import ReferenceQuery
from app.services.draft_api import DraftAPIService
from app.services.evidence import EvidenceConflict, EvidenceNotFound, EvidenceUnavailable

reference_env = reference_fixture
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("TRUEFLAG_TEST_POSTGRES_URL"),
        reason="verified native Linux/PostgreSQL required",
    ),
]


@pytest.fixture
def queued(reference_env):
    e = reference_env
    e["settings"].investigation_simulation_enabled = True
    e["settings"].regulatory_investigation_enabled = True
    gateway = DraftAPIService(e["engine"], e["settings"])
    coordinator = gateway.drafts.coordinator
    token = secrets.token_urlsafe(48)
    coordinator.register_worker(e["admin"], "queued-rag-native-fixture", token)
    context = coordinator.reader.get_case_context(e["analyst"], e["case"])
    request = InvestigationRequest(
        expected_case_version=context.snapshot.case_version,
        expected_evidence_revision=context.snapshot.evidence_revision,
        expected_access_revision=context.snapshot.access_revision,
        without_assessment_reason="not_selected",
        window={
            "start": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 11, 2, tzinfo=timezone.utc),
        },
        currencies=("USD",),
    )
    e.update(
        gateway=gateway,
        drafts=gateway.drafts,
        coordinator=coordinator,
        token=token,
        body=DraftStartInput(
            investigation_request=request, regulatory_query=ReferenceQuery(section="sar")
        ),
    )
    return e


def start(e, key="queued-regulatory-native-001"):
    return e["gateway"].start(e["analyst"], e["case"], key, e["body"])


def count(e, model):
    with Session(e["engine"]) as s:
        return s.scalar(select(func.count()).select_from(model))


def parent_done(e):
    value = e["coordinator"].run_once(e["token"])
    assert value["status"] == "abstained", value  # No transaction history invented.


def test_http_start_parent_binding_result_and_refresh_are_durable(queued):
    e = queued
    client = e["platform"][0]
    base = f"/api/v1/cases/{e['case']}/investigation-drafts"
    auth = {**headers(e["platform"], "analyst"), "Idempotency-Key": "queued-native-http"}
    assert client.post(base + "/start", json=e["body"].model_dump(mode="json")).status_code == 401
    response = client.post(base + "/start", json=e["body"].model_dump(mode="json"), headers=auth)
    assert response.status_code == 202, response.text
    assert (
        client.post(base + "/start", json=e["body"].model_dump(mode="json"), headers=auth).json()
        == response.json()
    )
    assert count(e, DraftRegulatoryBinding) == count(e, DraftAttempt) == 0
    assert e["drafts"].claim(e["token"]) is None
    assert client.get(response.headers["location"], headers=auth).json()["status"] == "pending"
    parent_done(e)
    assert client.get(response.headers["location"], headers=auth).json()["status"] == "pending"
    assert e["drafts"].run_once(e["token"])["status"] == "abstained"
    first = client.get(response.headers["location"], headers=auth)
    refreshed = client.get(response.headers["location"], headers=auth)
    assert first.status_code == refreshed.status_code == 200
    assert first.json() == refreshed.json()
    assert first.json()["draft"]["regulatory_citations"]
    assert first.json()["draft"]["simulation"] is True
    assert count(e, DraftRegulatoryBinding) == count(e, StoredDraft) == count(e, DraftAttempt) == 1


def test_concurrent_start_and_changed_query_conflict(queued):
    e = queued
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(e), range(2)))
    assert results[0] == results[1] and count(e, DraftRun) == 1
    changed = e["body"].model_copy(update={"regulatory_query": ReferenceQuery(section="aml")})
    with pytest.raises(EvidenceConflict):
        e["gateway"].start(e["analyst"], e["case"], "queued-regulatory-native-001", changed)


def test_revocation_prevents_retrieval_and_provider_attempt(queued):
    e = queued
    start(e)
    parent_done(e)
    e["service"].grant(e["admin"], e["context"], e["analyst"], False)
    assert e["drafts"].run_once(e["token"])["status"] in {"failed", "invalidated"}
    assert count(e, DraftAttempt) == count(e, StoredDraft) == 0


def test_research_only_sources_cannot_reach_provider(queued):
    e = queued
    start(e)
    parent_done(e)
    e["settings"].app_env = "development"  # Fixture approval is not official authority.
    assert e["drafts"].run_once(e["token"])["status"] == "failed"
    assert count(e, DraftAttempt) == count(e, StoredDraft) == 0


def test_regrant_cannot_restore_old_admission_authority(queued):
    e = queued
    start(e)
    parent_done(e)
    e["service"].grant(e["admin"], e["context"], e["analyst"], False)
    e["service"].grant(e["admin"], e["context"], e["analyst"], True)
    assert e["drafts"].run_once(e["token"])["status"] == "failed"
    assert count(e, DraftAttempt) == count(e, StoredDraft) == 0


def test_assignment_isolation_on_start(queued):
    e = queued
    other = UUID(e["team"]["users"]["analysttwo"])
    with pytest.raises(EvidenceNotFound):
        e["gateway"].start(other, e["case"], "queued-wrong-analyst", e["body"])
    assert count(e, DraftRun) == 0


def test_binding_failure_rolls_back_before_reservation(queued, monkeypatch):
    e = queued
    start(e)
    parent_done(e)
    claim = e["drafts"].claim(e["token"])
    original = e["drafts"]._event

    def fail(session, run, action, **details):
        original(session, run, action, **details)
        if action == "regulatory_bound":
            raise RuntimeError("synthetic transaction fault")

    monkeypatch.setattr(e["drafts"], "_event", fail)
    with pytest.raises(EvidenceUnavailable):
        e["drafts"].prepare(e["token"], claim)
    assert count(e, DraftRegulatoryBinding) == count(e, DraftAttempt) == 0


def test_database_rejects_attempt_before_worker_binding(queued):
    e = queued
    status = start(e)
    parent_done(e)
    with pytest.raises(DBAPIError, match="missing_queued_regulatory_binding"):
        with Session(e["engine"]) as s, s.begin():
            s.add(
                DraftAttempt(
                    id=uuid4(),
                    run_id=status.draft_run_id,
                    attempt=1,
                    lease_sha256="a" * 64,
                    packet_sha256="b" * 64,
                    minimized_sha256="c" * 64,
                    input_reservation=1024,
                    output_reservation=256,
                )
            )
            s.flush()
    assert count(e, DraftAttempt) == 0


def test_simulation_recovery_keeps_one_original_binding(queued):
    e = queued
    status = start(e)
    parent_done(e)
    claim = e["drafts"].claim(e["token"])
    e["drafts"].prepare(e["token"], claim)
    with Session(e["engine"]) as s:
        original = s.get(DraftRegulatoryBinding, status.draft_run_id).body
    with e["engine"].begin() as c:
        c.execute(
            text(
                "UPDATE investigation_draft_jobs SET deadline=clock_timestamp()-interval '1 second', lease_until=clock_timestamp()-interval '1 second' WHERE run_id=:run"
            ),
            {"run": status.draft_run_id},
        )
    assert e["drafts"].recover(e["token"]) == 1
    with e["engine"].begin() as c:
        c.execute(
            text(
                "UPDATE investigation_draft_jobs SET not_before=clock_timestamp()-interval '1 second' WHERE run_id=:run"
            ),
            {"run": status.draft_run_id},
        )
    assert e["drafts"].run_once(e["token"])["status"] == "abstained"
    with Session(e["engine"]) as s:
        assert s.get(DraftRegulatoryBinding, status.draft_run_id).body == original
    assert count(e, DraftRegulatoryBinding) == count(e, StoredDraft) == 1


def test_candidate_downgrade_preserves_retained_deferred_intents(queued):
    e = queued
    start(e)
    config = Config("backend/alembic.ini")
    with pytest.raises(RuntimeError, match="Refusing to remove safeguards"):
        command.downgrade(config, "0022_claude_development_scope")
    with e["engine"].connect() as c:
        assert (
            c.scalar(text("SELECT version_num FROM alembic_version"))
            == "0023_durable_regulatory_start"
        )
