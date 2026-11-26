"""Isolated PostgreSQL ledger and schema checks; no provider or network calls."""

import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as existing_draft_env
from test_investigation_drafts import env as evidence_env
from test_investigation_drafts import evidence_setup as evidence_fixture
from test_investigation_drafts import ready

import app.core.release as release
import app.core.release_metadata as release_metadata
from app.core.schema import EXPECTED_SCHEMA_REVISION
from app.models import AuditEvent
from app.models.investigation_drafts import DraftAttempt, DraftReceipt, StoredDraft
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.provider_live import ClaudeProviderConfig
from app.services.claude_contract import output_schema
from app.services.claude_provider import ClaudeProvider
from app.services.evidence import EvidenceConflict
from app.services.ingestion import digest
from app.services.investigation_draft_verifier import minimize
from app.services.provider_finance import reservation_totals

pytestmark = pytest.mark.postgres
draft_env = existing_draft_env
env = evidence_env
evidence_setup = evidence_fixture


@pytest.fixture(autouse=True)
def candidate_release(monkeypatch):
    # This test's fixture migrates only a disposable schema; the running demo remains on 0019.
    revision = max(EXPECTED_SCHEMA_REVISION, "0020_claude_provider")
    monkeypatch.setattr(release, "EXPECTED_SCHEMA_REVISION", revision)
    monkeypatch.setattr(release_metadata, "EXPECTED_SCHEMA_REVISION", revision)
    monkeypatch.setattr(release, "load_identity", lambda: release_metadata.unknown_identity())


def test_candidate_migration_and_immutable_reservation(draft_env):
    e = draft_env
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_contract_verified = True
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd=Decimal("2.10"),
    )
    with e["platform"][1].connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == max(
            EXPECTED_SCHEMA_REVISION, "0020_claude_provider"
        )
        function = connection.scalar(
            text("SELECT pg_get_functiondef('require_draft_envelope()'::regprocedure)")
        )
        assert "anthropic" in function and "synthetic_only" in function
    ready(e, config=config)
    claim = e["drafts"].claim(e["token"])
    assert claim is not None
    assert e["drafts"].prepare(e["token"], claim) is not None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal("2.10"))
        assert reservation_totals(session, provider="luminal") == (0, Decimal(0))
        assert len(session.scalars(select(DraftAttempt)).all()) == 1
    with pytest.raises(EvidenceConflict, match="draft_attempt_already_reserved"):
        e["drafts"].prepare(e["token"], claim)


def test_live_validation_one_reservation_per_wire_contract(draft_env):
    e = draft_env
    from uuid import UUID

    actor, case, token = e["users"]["admin"], e["case"], e["token"]
    parent = e["service"].request(actor, case, "live-validation-parent", packet_request(e))
    assert e["service"].run_once(token)["status"] == "succeeded"
    packet = InvestigationPacketBody.model_validate(
        e["service"].get(actor, case, UUID(parent["run_id"]))["packet"]
    )
    exact = digest(minimize(packet).model_dump(mode="json"))
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_contract_verified = False
    settings.anthropic_live_validation_enabled = True
    settings.anthropic_live_validation_input_sha256 = exact
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd="2.15",
        purpose="live_validation",
        exact_input_sha256=exact,
    )
    e["drafts"].request(actor, case, "live-validation-first", packet_request(e), config)
    first = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, first) is not None
    e["drafts"].fail(token, first, "provider_timeout")
    different = config.model_copy(update={"max_cost_usd": Decimal("2.16")})
    e["drafts"].request(actor, case, "live-validation-retry", packet_request(e), different)
    second = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, second) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal("2.15"))


def test_bootstrap_is_exact_and_cannot_be_reserved_twice(draft_env):
    e = draft_env
    actor, case, token = e["users"]["admin"], e["case"], e["token"]
    parent = e["service"].request(actor, case, "claude-probe-parent", packet_request(e))
    assert e["service"].run_once(token)["status"] == "succeeded"
    from uuid import UUID

    view = e["service"].get(actor, case, UUID(parent["run_id"]))
    packet = InvestigationPacketBody.model_validate(view["packet"])
    exact = digest(minimize(packet).model_dump(mode="json"))
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_bootstrap_enabled = True
    settings.anthropic_contract_verified = False
    settings.anthropic_bootstrap_input_sha256 = exact
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd=Decimal("2.10"),
        purpose="compatibility_probe",
        exact_input_sha256=exact,
    )
    e["drafts"].request(actor, case, "claude-probe-first", packet_request(e), config)
    first = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, first) is not None
    e["drafts"].fail(token, first, "provider_timeout")
    second_config = ClaudeProviderConfig.model_validate(
        {**config.model_dump(), "max_cost_usd": "2.20"}
    )
    e["drafts"].request(actor, case, "claude-probe-second", packet_request(e), second_config)
    second = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, second) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal("2.10"))
    settings.anthropic_diagnostic_enabled = True
    settings.anthropic_diagnostic_input_sha256 = exact
    diagnostic = ClaudeProviderConfig.model_validate(
        {**config.model_dump(), "purpose": "compatibility_diagnostic"}
    )
    e["drafts"].request(actor, case, "claude-diagnostic-first", packet_request(e), diagnostic)
    diagnostic_claim = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, diagnostic_claim) is not None
    e["drafts"].fail(token, diagnostic_claim, "provider_timeout")
    diagnostic_again = ClaudeProviderConfig.model_validate(
        {**diagnostic.model_dump(), "max_cost_usd": "2.20"}
    )
    e["drafts"].request(
        actor, case, "claude-diagnostic-second", packet_request(e), diagnostic_again
    )
    second_diagnostic = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, second_diagnostic) is not None
    e["drafts"].fail(
        token,
        second_diagnostic,
        "provider_unavailable",
        diagnostics={
            "parseable": True,
            "model_matches": True,
            "stop_reason": "end_turn",
            "text_blocks": 1,
            "other_blocks": 0,
            "schema_valid": False,
            "schema_errors": ["packet_sha256:string_pattern_mismatch"],
            "input_tokens": 10,
            "output_tokens": 10,
            "cache_tokens": 0,
        },
    )
    third_diagnostic = ClaudeProviderConfig.model_validate(
        {**diagnostic.model_dump(), "max_cost_usd": "2.30"}
    )
    e["drafts"].request(actor, case, "claude-diagnostic-third", packet_request(e), third_diagnostic)
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (3, Decimal("6.40"))
    settings.anthropic_fix_verification_enabled = True
    settings.anthropic_fix_input_sha256 = exact
    fix = ClaudeProviderConfig.model_validate(
        {**diagnostic.model_dump(), "purpose": "compatibility_fix_verification"}
    )
    e["drafts"].request(actor, case, "claude-fix-first", packet_request(e), fix)
    fix_claim = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, fix_claim) is not None
    e["drafts"].fail(
        token, fix_claim, "verification_failed", verification_reason="question_mismatch"
    )
    second_fix = ClaudeProviderConfig.model_validate({**fix.model_dump(), "max_cost_usd": "2.30"})
    e["drafts"].request(actor, case, "claude-fix-second", packet_request(e), second_fix)
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (4, Decimal("8.50"))
    settings.anthropic_verification_diagnostic_enabled = True
    settings.anthropic_verification_input_sha256 = exact
    verification = ClaudeProviderConfig.model_validate(
        {**diagnostic.model_dump(), "purpose": "verification_diagnostic"}
    )
    e["drafts"].request(actor, case, "claude-verification-first", packet_request(e), verification)
    verification_claim = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, verification_claim) is not None
    e["drafts"].fail(
        token, verification_claim, "verification_failed", verification_reason="claim_type_mismatch"
    )
    second_verification = ClaudeProviderConfig.model_validate(
        {**verification.model_dump(), "max_cost_usd": "2.30"}
    )
    e["drafts"].request(
        actor, case, "claude-verification-second", packet_request(e), second_verification
    )
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (5, Decimal("10.60"))
    settings.anthropic_claim_fix_enabled = True
    settings.anthropic_claim_fix_input_sha256 = exact
    claim_fix = ClaudeProviderConfig.model_validate(
        {**diagnostic.model_dump(), "purpose": "claim_type_fix_verification"}
    )
    e["drafts"].request(actor, case, "claude-claim-fix-first", packet_request(e), claim_fix)
    first_claim_fix = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, first_claim_fix) is not None
    e["drafts"].fail(token, first_claim_fix, "provider_timeout")
    next_fix = ClaudeProviderConfig.model_validate(
        {**claim_fix.model_dump(), "max_cost_usd": "2.40"}
    )
    e["drafts"].request(actor, case, "claude-claim-fix-second", packet_request(e), next_fix)
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (6, Decimal("12.70"))


def test_claim_fix_denied_without_matching_failed_diagnostic(draft_env):
    e = draft_env
    actor, case, token = e["users"]["admin"], e["case"], e["token"]
    parent = e["service"].request(actor, case, "claim-no-prior-parent", packet_request(e))
    assert e["service"].run_once(token)["status"] == "succeeded"
    from uuid import UUID

    view = e["service"].get(actor, case, UUID(parent["run_id"]))
    exact = digest(
        minimize(InvestigationPacketBody.model_validate(view["packet"])).model_dump(mode="json")
    )
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_claim_fix_enabled = True
    settings.anthropic_claim_fix_input_sha256 = exact
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd=Decimal("2.14"),
        purpose="claim_type_fix_verification",
        exact_input_sha256=exact,
    )
    e["drafts"].request(actor, case, "claim-fix-no-prior", packet_request(e), config)
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (0, Decimal(0))


@pytest.mark.parametrize(
    "attack", [None, "forged_reference", "incorrect_total", "source_revoked", "malformed_output"]
)
def test_durable_worker_verifies_claude_response_before_publication(draft_env, attack):
    e = draft_env
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_contract_verified = True
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_api_key = SecretStr("offline-test-only")
    config = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd=Decimal("2.10"),
    )
    ready(e, config=config)
    calls = []

    class ResponseStream(httpx.SyncByteStream):
        def __init__(self, content):
            self.content = content

        def __iter__(self):
            yield self.content

    def response_for(request):
        calls.append(request)
        if attack == "source_revoked":
            e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
        body = json.loads(request.content)
        packet = json.loads(body["messages"][0]["content"])
        record = packet["transactions"][0]["reference_id"]
        if attack == "forged_reference":
            record = str(uuid4())
        finding = {
            "claim_type": "observed_fact",
            "reference_id": record,
            "supporting_evidence": [record],
            "contradictory_evidence": [],
            "numeric_statements": [],
        }
        if attack == "incorrect_total":
            finding["numeric_statements"] = [{"metric": "amount", "value": "99999999"}]
        proposal = {
            "packet_sha256": packet["packet_sha256"],
            "overview": "review_supplied_evidence",
            "supporting_records": [record],
            "financial_observations": [],
            "unusual_activity": [finding],
            "model_signals": [],
            "risk_indicators": [],
            "missing_or_contradictory_evidence": packet["missing_evidence"] + packet["conflicts"],
            "follow_up_questions": packet["questions"],
            "additional_information_needed": packet["questions"],
            "uncertainty_limitations": packet["limitations"],
            "next_steps": ["human_review"],
            "abstain": False,
            "uncertainty": "requires_human_semantic_review",
        }
        response = {
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(proposal)}],
            "usage": {"input_tokens": 500, "output_tokens": 300},
        }
        if attack == "malformed_output":
            response["stop_reason"] = "max_tokens"
            response["content"][0]["text"] = "do not retain private response"
        return httpx.Response(
            200,
            stream=ResponseStream(json.dumps(response).encode()),
            headers={"content-type": "application/json"},
        )

    class MockRunner:
        def invoke(self, packet, config):
            return ClaudeProvider(settings, transport=httpx.MockTransport(response_for)).propose(
                packet, config
            )

    e["drafts"]._runner = MockRunner()
    result = e["drafts"].run_once(e["token"])
    assert len(calls) == 1
    if attack is None:
        assert result["status"] == "succeeded"
    elif attack == "source_revoked":
        assert result["status"] == "invalidated"
    elif attack == "malformed_output":
        # The provider answered (HTTP 200) but the output failed the local contract.
        assert result["status"] == "failed" and result["error_code"] == "invalid_provider_output"
    else:
        assert result["status"] == "failed" and result["error_code"] == "verification_failed"
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal("2.10"))
        assert len(session.scalars(select(StoredDraft)).all()) == (1 if attack is None else 0)
        if attack == "malformed_output":
            receipt = session.scalar(select(DraftReceipt))
            assert receipt.status == "invalid_provider_output"
            assert receipt.usage["input_tokens"] == 500 and receipt.usage["output_tokens"] == 300
            assert receipt.usage["diagnostics"]["stop_reason"] == "max_tokens"
            assert "do not retain" not in json.dumps(receipt.usage)
        if attack in {"forged_reference", "incorrect_total"}:
            event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence.investigation.draft.attempt_failed"
                )
            )
            expected = (
                "supporting_reference_invalid"
                if attack == "forged_reference"
                else "numeric_value_mismatch"
            )
            assert event.details["verification_reason"] == expected
