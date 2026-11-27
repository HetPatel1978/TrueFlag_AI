"""Real isolated PostgreSQL coordinator/persistence, mock external HTTP. Zero provider egress."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as draft_fixture
from test_investigation_drafts import ready as fake_ready
from test_luminal_provider import config, envelope, proposal, response, settings

from alembic import command
from app.models import AuditEvent, Case
from app.models.investigation_drafts import DraftAttempt, DraftJob, DraftReceipt, StoredDraft
from app.services.evidence import EvidenceBlocked
from app.services.investigation_drafts import InvestigationDraftService
from app.services.luminal_provider import LuminalProvider

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture
draft_env = draft_fixture


def test_migration_roundtrip_preserves_existing_simulation_history(draft_env):
    from conftest import BACKEND

    receipt = fake_ready(draft_env)
    assert draft_env["drafts"].run_once(draft_env["token"])["status"] == "succeeded"
    with Session(draft_env["platform"][1]) as session:
        original = session.scalar(select(StoredDraft.content_sha256))
    cfg = Config(str(BACKEND / "alembic.ini"))
    command.downgrade(cfg, "0016_snapshot_clock")
    command.upgrade(cfg, "head")
    with Session(draft_env["platform"][1]) as session:
        assert session.scalar(select(StoredDraft.content_sha256)) == original
    assert (
        draft_env["drafts"].get(
            draft_env["users"]["admin"], draft_env["case"], UUID(receipt["draft_run_id"])
        )["draft"]["mode"]
        == "simulation"
    )


def setup(env, *, handler=None, cfg=None, provider_settings=None):
    for name, value in vars(settings(**(provider_settings or {}))).items():
        setattr(env["platform"][2], name, value)
    service = InvestigationDraftService(env["platform"][1], env["platform"][2])
    calls = []

    def transport(req):
        calls.append(req)
        data = json.loads(json.loads(req.content)["messages"][1]["content"])
        from app.schemas.investigation_drafts import ProviderInput

        value = ProviderInput.model_validate(data)
        return handler(value) if handler else response(envelope(proposal(value).model_dump_json()))

    adapter = LuminalProvider(env["platform"][2], transport=httpx.MockTransport(transport))

    class MockHTTPRunner:
        def invoke(self, packet, cfg):
            return adapter.propose(packet, cfg)

    service._runner = MockHTTPRunner()
    receipt = service.request(
        env["users"]["admin"],
        env["case"],
        "mock-live-request-001",
        packet_request(env),
        cfg or config(),
    )
    assert env["service"].run_once(env["token"])["status"] in {"succeeded", "abstained"}
    return service, receipt, calls


def test_mock_provider_coordinator_verification_and_atomic_immutable_persistence(env):
    service, receipt, calls = setup(env)
    result = service.run_once(env["token"])
    assert (
        result["status"] == "succeeded"
        and result["mode"] == "provider_candidate"
        and len(calls) == 1
    )
    value = service.get(env["users"]["admin"], env["case"], UUID(receipt["draft_run_id"]))["draft"]
    assert value["schema_version"] == "trueflag.ai-investigation-draft.v1"
    assert value["financial_observations"] and value["unusual_activity"]
    assert value["regulatory_citations"] == [] and value["human_conclusions"] == []
    assert value["verification"]["full_factual_entailment_verified"] is False
    with Session(env["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(StoredDraft)) == 1
        assert s.scalar(select(func.count()).select_from(DraftReceipt)) == 1
        assert s.scalar(select(DraftReceipt.elapsed_ms)) is not None
        assert s.get(Case, env["case"]).status == "open"
        audits = json.dumps([a.details for a in s.scalars(select(AuditEvent))])
        assert "synthetic-unit-key" not in audits
    assert service.run_once(env["token"]) is None and len(calls) == 1


def test_database_publication_failure_rolls_back_candidate_result_without_paid_retry(env):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    service, _, calls = setup(env)

    def failure(connection, cursor, statement, *args):
        if statement.lower().lstrip().startswith("insert into investigation_drafts "):
            raise OperationalError(
                "synthetic-private-db-marker", None, RuntimeError("must-not-leak")
            )

    engine = env["platform"][1]
    event.listen(engine, "before_cursor_execute", failure)
    try:
        result = service.run_once(env["token"])
    finally:
        event.remove(engine, "before_cursor_execute", failure)
    assert result["status"] == "failed" and result["error_code"] == "database_unavailable"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0
        assert session.scalar(select(func.count()).select_from(DraftReceipt)) == 1
        assert session.scalar(select(DraftReceipt.status)) == "database_unavailable"
        assert session.get(Case, env["case"]).status == "open"
    assert len(calls) == 1 and service.run_once(env["token"]) is None


@pytest.mark.parametrize(
    "attack",
    [
        "foreign_reference",
        "amount",
        "unsupported_prose",
        "gap_omission",
        "wrong_section",
        "packet_identity",
    ],
)
def test_unknown_evidence_numbers_and_unsupported_claims_are_not_publishable(env, attack):
    def handler(packet):
        data = proposal(packet).model_dump(mode="json")
        if attack == "foreign_reference":
            data["unusual_activity"][0]["reference_id"] = str(uuid4())
        if attack == "amount":
            data["unusual_activity"][0]["numeric_statements"] = [
                dict(metric="amount", value="999999999", currency="USD", window=None, feature=None)
            ]
        if attack == "unsupported_prose":
            data["criminal_conclusion"] = "criminal"
        if attack == "gap_omission":
            data["missing_or_contradictory_evidence"] = []
        if attack == "wrong_section":
            data["financial_observations"] = data["unusual_activity"]
        if attack == "packet_identity":
            data["packet_sha256"] = "b" * 64
        return response(envelope(json.dumps(data)))

    service, _, calls = setup(env, handler=handler)
    result = service.run_once(env["token"])
    assert result["status"] == "failed" and len(calls) == 1
    with Session(env["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(StoredDraft)) == 0


def test_source_revocation_during_mock_request_prevents_publication(env):
    def handler(packet):
        env["foundation"].set_source_access(
            env["users"]["admin"], env["case"], env["source"], False
        )
        return response(envelope(proposal(packet).model_dump_json()))

    service, _, _ = setup(env, handler=handler)
    assert service.run_once(env["token"])["status"] == "invalidated"
    with Session(env["platform"][1]) as s:
        assert s.scalar(select(func.count()).select_from(StoredDraft)) == 0


def test_withdrawn_provider_authorization_cannot_dispatch(env):
    service, _, calls = setup(env)
    env["platform"][2].investigation_provider_contract_verified = False
    with pytest.raises(EvidenceBlocked):
        service.run_once(env["token"])
    assert calls == []


def test_crash_after_reservation_is_not_automatically_redispatched(env):
    service, receipt, calls = setup(env)
    claim = service.claim(env["token"])
    assert service.prepare(env["token"], claim)
    with Session(env["platform"][1]) as s, s.begin():
        job = s.get(DraftJob, UUID(receipt["draft_run_id"]))
        job.deadline = job.lease_until = s.scalar(select(func.clock_timestamp())) - timedelta(
            seconds=1
        )
    assert service.recover(env["token"]) == 1
    with Session(env["platform"][1]) as s:
        job = s.get(DraftJob, UUID(receipt["draft_run_id"]))
        assert job.status == "failed" and job.attempts == 1
        assert s.scalar(select(func.count()).select_from(DraftAttempt)) == 1
    assert calls == [] and service.run_once(env["token"]) is None


def test_live_rate_rejection_never_schedules_paid_retry(env):
    service, receipt, calls = setup(
        env,
        handler=lambda p: response({}, 429, **{"retry-after": "20"}),
        cfg=config(max_attempts=1),
    )
    result = service.run_once(env["token"])
    assert result["status"] == "failed"
    with Session(env["platform"][1]) as s:
        job = s.get(DraftJob, UUID(receipt["draft_run_id"]))
        assert job.attempts == 1
    assert service.run_once(env["token"]) is None and len(calls) == 1


def test_grant_spend_reservations_remain_charged_after_ambiguous_delivery(env):
    def timeout(packet):
        raise httpx.ReadError("synthetic-ambiguous-delivery")

    service, _, calls = setup(env, handler=timeout, cfg=config(max_cost_usd="0.1"))
    env["platform"][2].investigation_provider_spend_limit_usd = 0.1
    assert service.run_once(env["token"])["status"] == "failed"
    # A distinct intent shares the same approval budget; the uncertain first attempt is retained.
    service.request(
        env["users"]["admin"],
        env["case"],
        "second-grant-intent",
        packet_request(env),
        config(max_cost_usd="0.1", max_output_tokens=4097, total_token_budget=36865),
    )
    env["service"].run_once(env["token"])
    result = service.run_once(env["token"])
    assert result["status"] == "failed" and result["error_code"] == "budget_exhausted"
    assert len(calls) == 1
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1


def test_clock_health_denial_prevents_mock_dispatch(env, monkeypatch):
    from app.services.evidence import EvidenceError
    from app.services.snapshot_clock import ClockUnavailable

    service, _, calls = setup(env)

    def denied(*a, **k):
        raise ClockUnavailable("snapshot_clock_unavailable")

    monkeypatch.setattr(service.coordinator.reader.clock, "observe", denied)
    with pytest.raises((ClockUnavailable, EvidenceError)):
        service.run_once(env["token"])
    assert calls == []


def test_candidate_duplicate_requests_have_one_intent_and_one_completion(env):
    from concurrent.futures import ThreadPoolExecutor

    service, receipt, calls = setup(env)
    request = packet_request(env)

    def submit(_):
        return service.request(
            env["users"]["admin"], env["case"], "mock-live-request-001", request, config()
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(submit, range(3)))
    assert {r["draft_run_id"] for r in rows} == {receipt["draft_run_id"]}
    assert service.run_once(env["token"])["status"] == "succeeded" and len(calls) == 1


def test_migration_rehearsal_retains_fake_history_and_blocks_candidate_history_downgrade(env):
    from conftest import BACKEND

    cfg = Config(str(BACKEND / "alembic.ini"))
    command.downgrade(cfg, "0016_snapshot_clock")
    command.upgrade(cfg, "head")
    service, _, _ = setup(env)
    assert service.run_once(env["token"])["status"] == "succeeded"
    with pytest.raises(RuntimeError, match="retained external draft history"):
        command.downgrade(cfg, "0016_snapshot_clock")
