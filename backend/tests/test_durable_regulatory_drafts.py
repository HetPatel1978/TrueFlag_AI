"""Candidate PostgreSQL immutable regulatory bindings over the existing durable worker."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_references import reference_env as reference_fixture
from test_regulatory_investigation import grounded as grounding_fixture

from alembic import command
from app.models.investigation_drafts import DraftJob, StoredDraft
from app.models.regulatory_drafts import DraftRegulatoryBinding
from app.schemas.draft_api import DraftRequestInput
from app.schemas.investigations import InputManifest
from app.schemas.provider_live import GroundedSimulationConfig
from app.services.draft_api import DraftAPIService
from app.services.evidence import EvidenceConflict, EvidenceNotFound, EvidenceUnavailable
from app.services.ingestion import digest
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_provider import DeterministicFakeProvider
from app.services.investigation_verifier import VerificationFailed

reference_env = reference_fixture
grounded = grounding_fixture
pytestmark = pytest.mark.postgres


def test_candidate_migration_empty_rollback_and_reupgrade(reference_env):
    e = reference_env
    config = Config("backend/alembic.ini")
    config.set_main_option("script_location", "backend/alembic")
    command.downgrade(config, "0020_claude_provider")
    with e["engine"].connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('draft_regulatory_bindings')")) is None
    command.upgrade(config, "0021_regulatory_draft_bindings")
    with e["engine"].connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('draft_regulatory_bindings')"))


@pytest.fixture
def durable(grounded):
    e, bridge, parent_id, binding = grounded
    settings = e["settings"]
    settings.investigation_simulation_enabled = True
    settings.regulatory_investigation_enabled = True
    token = secrets.token_urlsafe(48)
    bridge.coordinator.register_worker(e["admin"], "durable-grounding-worker", token)
    with Session(e["engine"]) as session:
        parent = bridge.coordinator._run(session, parent_id)
        request = InputManifest.model_validate(parent.input_manifest).request
    service = InvestigationDraftService(e["engine"], settings)
    config = GroundedSimulationConfig(regulatory_binding_sha256=binding.binding_sha256)
    return e, service, token, request, config, binding


def submit(d, key="durable-grounding-001"):
    e, service, _, request, config, binding = d
    return service.request(e["analyst"], e["case"], key, request, config, binding)


def test_context_is_persisted_once_and_existing_worker_publishes_it(durable):
    e, service, token, _, _, binding = durable
    receipt = submit(durable)
    assert submit(durable)["draft_run_id"] == receipt["draft_run_id"]
    result = service.run_once(token)
    assert result["status"] == "abstained"
    run = UUID(receipt["draft_run_id"])
    view = service.get(e["analyst"], e["case"], run)
    body = view["draft"]
    assert body["regulatory_binding_sha256"] == binding.binding_sha256
    assert body["regulatory_citations"][0]["reference_id"] == str(
        binding.result.passages[0].reference_id
    )
    assert body["provenance"]["simulation"] is True
    with Session(e["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRegulatoryBinding)) == 1
        assert session.get(DraftRegulatoryBinding, run).body == binding.model_dump(mode="json")


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE draft_regulatory_bindings SET binding_sha256='forged'",
        "DELETE FROM draft_regulatory_bindings",
        "TRUNCATE draft_regulatory_bindings",
    ],
)
def test_binding_is_database_immutable(durable, operation):
    e, *_ = durable
    submit(durable)
    with pytest.raises(DBAPIError):
        with e["engine"].begin() as connection:
            connection.execute(text(operation))


@pytest.mark.parametrize("phase", ["dispatch", "completion", "read", "regrant"])
def test_revoked_context_cannot_dispatch_publish_or_be_read(durable, phase):
    e, service, token, *_ = durable
    receipt = submit(durable)
    run = UUID(receipt["draft_run_id"])
    if phase == "completion":

        class RevokeRunner:
            def invoke(self, packet, config):
                e["service"].grant(e["admin"], e["context"], e["analyst"], False)
                return DeterministicFakeProvider().propose(packet, config)

        service._runner = RevokeRunner()
    elif phase == "read":
        assert service.run_once(token)["status"] == "abstained"
        e["service"].withdraw(e["admin"], release_id=durable[-1].result.release_id)
    else:
        e["service"].grant(e["admin"], e["context"], e["analyst"], False)
        if phase == "regrant":
            e["service"].grant(e["admin"], e["context"], e["analyst"], True)
    if phase == "read":
        with pytest.raises((EvidenceNotFound, VerificationFailed)):
            service.get(e["analyst"], e["case"], run)
    else:
        outcome = service.run_once(token)
        assert outcome["status"] in {"failed", "invalidated"}
        with Session(e["engine"]) as session:
            assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0


def test_concurrent_requests_create_one_job_and_binding(durable):
    e, *_ = durable
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: submit(durable), range(2)))
    assert values[0]["draft_run_id"] == values[1]["draft_run_id"]
    with Session(e["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRegulatoryBinding)) == 1


def test_failed_binding_insert_rolls_back_job_and_audit(durable, monkeypatch):
    e, service, *_ = durable
    original = service._event

    def fail(session, run, action, **details):
        original(session, run, action, **details)
        if action == "requested":
            raise RuntimeError("synthetic rollback injection")

    monkeypatch.setattr(service, "_event", fail)
    with pytest.raises(EvidenceUnavailable):
        submit(durable)
    with Session(e["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRegulatoryBinding)) == 0
        assert session.scalar(select(func.count()).select_from(DraftJob)) == 0


def test_api_retry_reuses_frozen_binding_and_rejects_different_query(durable):
    e, _, _, _, _, binding = durable
    key = "frozen-api-binding-retry"
    first = submit(durable, key)
    gateway = DraftAPIService(e["engine"], e["settings"])
    body = DraftRequestInput(
        investigation_run_id=binding.investigation_run_id,
        expected_packet_sha256=binding.packet_sha256,
        regulatory_query=binding.query,
    )
    assert (
        str(gateway.request(e["analyst"], e["case"], key, body).draft_run_id)
        == first["draft_run_id"]
    )
    changed = body.model_copy(
        update={"regulatory_query": binding.query.model_copy(update={"section": "aml"})}
    )
    with pytest.raises(EvidenceConflict):
        gateway.request(e["analyst"], e["case"], key, changed)


def test_expired_binding_is_not_renewed_by_retry(durable):
    e, service, _, request, config, binding = durable
    old = binding.model_copy(
        update={
            "prepared_second": binding.prepared_second - 901,
            "expires_second": binding.expires_second - 901,
        }
    )
    old = old.model_copy(
        update={"binding_sha256": digest(old.model_dump(mode="json", exclude={"binding_sha256"}))}
    )
    config = config.model_copy(update={"regulatory_binding_sha256": old.binding_sha256})
    with pytest.raises(VerificationFailed):
        service.request(e["analyst"], e["case"], "expired-grounding-key", request, config, old)


def test_worker_crash_recovery_keeps_one_binding_and_result(durable):
    e, service, token, *_ = durable
    receipt = submit(durable)
    claim = service.claim(token)
    assert service.prepare(token, claim) is not None
    with e["engine"].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_draft_jobs SET deadline=clock_timestamp()-interval '1 second', lease_until=clock_timestamp()-interval '1 second' WHERE run_id=:run"
            ),
            {"run": UUID(receipt["draft_run_id"])},
        )
    assert service.recover(token) == 1
    with e["engine"].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_draft_jobs SET not_before=clock_timestamp()-interval '1 second' WHERE run_id=:run"
            ),
            {"run": UUID(receipt["draft_run_id"])},
        )
    assert service.run_once(token)["status"] == "abstained"
    with Session(e["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRegulatoryBinding)) == 1
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 1


def test_simultaneous_workers_do_not_duplicate_publication(durable):
    e, service, token, *_ = durable
    submit(durable)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.run_once(token), range(2)))
    assert sum(value is not None and value["status"] == "abstained" for value in results) == 1
    with Session(e["engine"]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 1
