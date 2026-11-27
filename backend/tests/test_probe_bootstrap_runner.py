"""Mock-only bootstrap tests on isolated PostgreSQL; no provider egress."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_investigation_drafts import draft_env as draft_env_fixture
from test_investigation_drafts import env, evidence_setup, ready  # noqa: F401
from test_luminal_provider import envelope, response

from app.models import User
from app.models.investigation_drafts import DraftAttempt, DraftReceipt, DraftRun, StoredDraft
from app.models.investigations import InvestigationPacket
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.provider_live import AIProposal, LiveProviderConfig
from app.services.evidence import EvidenceBlocked, EvidenceError, EvidenceNotFound
from app.services.ingestion import digest
from app.services.luminal_bootstrap import OneAttemptProbeBootstrap, VerifiedProbe
from app.services.snapshot_clock import ClockUnavailable

pytestmark = pytest.mark.postgres
draft_env = draft_env_fixture


@pytest.fixture
def mock_probe(draft_env, monkeypatch):
    from app.services import luminal_bootstrap as bootstrap
    from app.services import luminal_provider as provider

    receipt = ready(draft_env)
    original_id = UUID(receipt["draft_run_id"])
    with Session(draft_env["platform"][1]) as session:
        run = session.get(DraftRun, original_id)
        record = session.scalar(
            select(InvestigationPacket).where(InvestigationPacket.run_id == run.parent_run_id)
        )
        packet = InvestigationPacketBody.model_validate_json(json.dumps(record.body))
    wire = b"synthetic-mocked-only-probe-wire"
    sha = hashlib.sha256(wire).hexdigest()
    config = LiveProviderConfig(
        approval_id="synthetic-mock-only",
        terms_sha256="a" * 64,
        max_input_tokens=8192,
        max_output_tokens=512,
        total_token_budget=8704,
        max_request_bytes=8192,
        max_attempts=1,
        input_usd_per_million=Decimal("0.2850"),
        output_usd_per_million=Decimal("1.1400"),
        max_cost_usd=Decimal("0.00992256"),
    )
    monkeypatch.setattr(bootstrap, "PROBE_A_SHA", sha)
    monkeypatch.setattr(bootstrap, "_terms_contract_current", lambda: True)
    monkeypatch.setattr(bootstrap, "verify_probe_a", lambda *a: VerifiedProbe(packet, sha))
    monkeypatch.setattr(
        bootstrap,
        "prepare_request",
        lambda *a: (wire, {"configuration": config.model_dump(mode="json")}),
    )
    monkeypatch.setattr(bootstrap, "request_body", lambda *a: wire)
    monkeypatch.setattr(provider, "request_body", lambda *a: wire)
    settings = draft_env["platform"][2]
    settings.investigation_probe_bootstrap_enabled = True
    settings.investigation_provider_financial_policy = "bounded_probe_v3"
    settings.investigation_provider_api_key = SecretStr("synthetic-invalid-only")
    settings.investigation_provider_contract_verified = False
    proposal = AIProposal(
        packet_sha256=digest(packet.model_dump(mode="json")),
        overview="insufficient_evidence",
        supporting_records=[],
        financial_observations=[],
        unusual_activity=[],
        model_signals=[],
        risk_indicators=[],
        missing_or_contradictory_evidence=list(set(packet.missing_evidence + packet.conflicts)),
        follow_up_questions=packet.questions,
        additional_information_needed=packet.questions,
        uncertainty_limitations=packet.limitations,
        next_steps=["human_review"],
        abstain=True,
        uncertainty="requires_human_semantic_review",
    )
    return draft_env, original_id, packet, proposal, bootstrap


def test_unverified_billing_blocks_before_ledger_or_transport(mock_probe):
    case_env, original, _, _, _ = mock_probe
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(EvidenceBlocked, match="probe_billing_bound_unverified"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0
    assert not calls


def test_unverified_current_terms_block_before_ledger_or_transport(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    monkeypatch.setattr(bootstrap, "_terms_contract_current", lambda: False)
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(EvidenceBlocked, match="probe_terms_version_unverified"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0
    assert not calls


@pytest.mark.parametrize("invalid", ["disabled", "tampered_authorization"])
def test_disable_and_tampered_authorization_block_before_egress(
    mock_probe, monkeypatch, tmp_path, invalid
):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    if invalid == "disabled":
        case_env["platform"][2].investigation_probe_bootstrap_enabled = False
    else:
        tampered = tmp_path / "grant.json"
        tampered.write_text('{"maximum_attempts":10}', encoding="utf-8")
        monkeypatch.setattr(bootstrap, "AUTHORIZATION_PATH", tampered)
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(EvidenceBlocked, match="probe_authorization_unavailable"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0
    assert not calls


def test_one_mock_response_is_verified_and_cannot_be_repeated(mock_probe, monkeypatch):
    case_env, original, _, proposal, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        return response(envelope(proposal.model_dump_json()))

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["status"] == "validated" and result["http_status"] == 200
    assert result["contract_verified_changed"] is False
    with pytest.raises(EvidenceBlocked, match="probe_attempt_already_reserved"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
        assert session.scalar(select(DraftReceipt.status)) == "completed"
    assert len(calls) == 1 and not case_env["platform"][2].investigation_provider_contract_verified


def test_rejected_mock_response_retains_reservation_and_is_not_retried(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        return response({}, status=401)

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["status"] == "failed" and result["http_status"] == 401
    assert result["reservation_retained"] is True
    with pytest.raises(EvidenceBlocked, match="probe_attempt_already_reserved"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    assert len(calls) == 1


def test_concurrent_mock_submissions_reserve_at_most_once(mock_probe, monkeypatch):
    case_env, original, _, proposal, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        return response(envelope(proposal.model_dump_json()))

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )

    def submit(_):
        try:
            return service.run_once(
                case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
            )["status"]
        except EvidenceBlocked:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(results) == ["blocked", "validated"]
    assert len(calls) == 1


def test_mismatched_wire_is_denied_before_attempt(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    monkeypatch.setattr(bootstrap, "prepare_request", lambda *a: (b"not-approved", {}))
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(EvidenceBlocked, match="approved_case_or_payload_changed"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    assert not calls


def test_wrong_actor_is_denied_before_any_attempt(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(EvidenceNotFound):
        service.run_once(
            case_env["users"]["analyst"], original, case_env["token"], (b"a", b"b", b"c")
        )
    assert not calls


def test_clock_denial_blocks_reservation_and_transport(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )

    def deny_clock():
        raise ClockUnavailable("snapshot_clock_unavailable")

    monkeypatch.setattr(service.drafts.coordinator.reader.clock, "observe", deny_clock)
    with pytest.raises((EvidenceError, ClockUnavailable)):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 0
    assert not calls


def test_permission_revocation_during_mock_call_prevents_publication(mock_probe, monkeypatch):
    case_env, original, _, proposal, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        with Session(case_env["platform"][1]) as session, session.begin():
            session.get(User, case_env["users"]["admin"]).role = "analyst"
        return response(envelope(proposal.model_dump_json()))

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["status"] == "failed" and result["reservation_retained"]
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0
        assert session.scalar(select(func.count()).select_from(DraftAttempt)) == 1
    assert len(calls) == 1


def test_source_revocation_during_mock_call_prevents_publication(mock_probe, monkeypatch):
    case_env, original, _, proposal, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        case_env["foundation"].set_source_access(
            case_env["users"]["admin"], case_env["case"], case_env["source"], False
        )
        return response(envelope(proposal.model_dump_json()))

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["status"] == "failed" and result["reservation_retained"]
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0
    assert len(calls) == 1


def test_mock_timeout_retains_attempt_without_retry(mock_probe, monkeypatch):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("synthetic-timeout")

    service = OneAttemptProbeBootstrap(
        case_env["platform"][1], case_env["platform"][2], transport=httpx.MockTransport(handler)
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["reason"] == "provider_timeout" and result["reservation_retained"]
    with pytest.raises(EvidenceBlocked, match="probe_attempt_already_reserved"):
        service.run_once(
            case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
        )
    assert len(calls) == 1


@pytest.mark.parametrize("wrong_model", [False, True])
def test_invalid_mock_response_is_never_marked_compatible(mock_probe, monkeypatch, wrong_model):
    case_env, original, _, _, bootstrap = mock_probe
    monkeypatch.setattr(bootstrap, "_billing_contract_verified", lambda: True)
    value = envelope("{}")
    if wrong_model:
        value["model"] = "synthetic-wrong-model"
    service = OneAttemptProbeBootstrap(
        case_env["platform"][1],
        case_env["platform"][2],
        transport=httpx.MockTransport(lambda req: response(value)),
    )
    result = service.run_once(
        case_env["users"]["admin"], original, case_env["token"], (b"a", b"b", b"c")
    )
    assert result["status"] == "failed" and result["http_status"] == 200
    assert result["reason"] == "invalid_provider_output"
    assert not case_env["platform"][2].investigation_provider_contract_verified
    with Session(case_env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 0
