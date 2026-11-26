"""Disposable PostgreSQL development admission and independent completion tests. No egress."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as existing_draft_env
from test_investigation_drafts import env as evidence_env
from test_investigation_drafts import evidence_setup as evidence_fixture

from app.core.schema import EXPECTED_SCHEMA_REVISION
from app.models.investigation_drafts import DraftAttempt, DraftReceipt, StoredDraft
from app.schemas.investigation_drafts import ProviderReply, ReportedUsage
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.provider_live import ClaudeProviderConfig
from app.services.claude_contract import output_schema
from app.services.claude_wire_v2 import WireProposal
from app.services.ingestion import digest
from app.services.investigation_draft_verifier import minimize
from app.services.provider_finance import reservation_totals

pytestmark = pytest.mark.postgres
draft_env = existing_draft_env
env = evidence_env
evidence_setup = evidence_fixture


def ready(e):
    actor, case, token = e["users"]["admin"], e["case"], e["token"]
    parent = e["service"].request(actor, case, "development-parent", packet_request(e))
    assert e["service"].run_once(token)["status"] == "succeeded"
    body = e["service"].get(actor, case, UUID(parent["run_id"]))["packet"]
    packet = minimize(InvestigationPacketBody.model_validate(body))
    settings = e["platform"][2]
    settings.anthropic_synthetic_demo_enabled = True
    settings.anthropic_contract_verified = False
    settings.anthropic_api_key = SecretStr("offline-only")
    settings.anthropic_terms_sha256 = "a" * 64
    settings.anthropic_demo_spend_limit_usd = 0
    settings.anthropic_demo_call_limit = 0
    settings.anthropic_development_validation_enabled = True
    settings.anthropic_development_input_sha256 = digest(packet.model_dump(mode="json"))
    settings.anthropic_development_approval_id = "dev-" + uuid4().hex
    config = ClaudeProviderConfig(
        approval_id=settings.anthropic_development_approval_id,
        terms_sha256="a" * 64,
        purpose="development_validation",
        financial_scope="development_no_spend_cap_v1",
        wire_format="flat_selection_v2",
        max_cost_usd=0,
        wire_schema_sha256=digest(output_schema(wire_format="flat_selection_v2")),
        exact_input_sha256=settings.anthropic_development_input_sha256,
    )
    return actor, case, token, packet, config


def reply(packet, config, tamper=None):
    fact = packet.financial_facts[0]
    result = fact["result"]
    value = dict(
        packet_sha256=packet.packet_sha256,
        overview="review_supplied_evidence",
        supporting_records=[str(v) for v in packet.evidence_references],
        findings=[
            dict(
                claim_type="calculated_fact",
                reference_id=fact["reference_id"],
                supporting_evidence=fact["input_record_ids"],
                contradictory_evidence=[],
                numeric_statements=[
                    dict(
                        metric="observed_total",
                        value=result["observed_total"],
                        currency=result["currency"],
                        window_start=result["window"]["start"],
                        window_end=result["window"]["end"],
                        feature="",
                    )
                ],
            )
        ],
        hypotheses=[],
        missing_or_contradictory_evidence=packet.missing_evidence + packet.conflicts,
        follow_up_questions=packet.questions,
        additional_information_needed=packet.questions,
        uncertainty_limitations=packet.limitations,
        next_steps=["human_review"],
        abstain=packet.evidence_requires_abstention,
        uncertainty="requires_human_semantic_review",
    )
    if tamper == "amount":
        value["findings"][0]["numeric_statements"][0]["value"] = "999999.99"
    if tamper == "reference":
        value["findings"][0]["supporting_evidence"] = [str(uuid4())]
    local = WireProposal.model_validate(value).local_proposal()
    return ProviderReply(
        provider="anthropic",
        model=config.model,
        content=local.model_dump_json(),
        finish_reason="complete",
        usage=ReportedUsage(
            input_tokens=500,
            output_tokens=300,
            cost_usd="0.004",
            basis="provider_reported_tokens_configured_rate_estimate",
        ),
    )


@pytest.mark.parametrize("tamper", [None, "amount", "reference"])
def test_independent_completion_and_rejection(draft_env, tamper):
    e = draft_env
    actor, case, token, packet, config = ready(e)
    run = e["drafts"].request(actor, case, "development-draft", packet_request(e), config)

    class Runner:
        def invoke(self, p, c):
            return reply(p, c, tamper)

    e["drafts"]._runner = Runner()
    result = e["drafts"].run_once(token)
    assert result["status"] == ("succeeded" if tamper is None else "failed")
    if tamper:
        assert result["error_code"] == "verification_failed"
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal(0))
        receipt = session.scalars(select(DraftReceipt)).one()
        assert receipt.usage["cost_usd"] == "0.004"
        assert len(session.scalars(select(StoredDraft)).all()) == (1 if tamper is None else 0)
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == max(
            EXPECTED_SCHEMA_REVISION, "0022_claude_development_scope"
        )
    assert UUID(run["draft_run_id"])


def test_one_outstanding_and_consumed_approval(draft_env):
    e = draft_env
    actor, case, token, packet, config = ready(e)
    e["drafts"].request(actor, case, "first-dev", packet_request(e), config)
    first = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, first) is not None
    next_config = config.model_copy(update={"approval_id": "dev-" + uuid4().hex})
    e["platform"][2].anthropic_development_approval_id = next_config.approval_id
    e["drafts"].request(actor, case, "second-dev", packet_request(e), next_config)
    second = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, second) is None
    e["platform"][2].anthropic_development_approval_id = config.approval_id
    e["drafts"].fail(token, first, "provider_unavailable")
    e["drafts"].request(
        actor,
        case,
        "replay-dev",
        packet_request(e),
        config.model_copy(update={"max_input_tokens": 32769, "total_token_budget": 36865}),
    )
    assert e["drafts"].prepare(token, e["drafts"].claim(token)) is None
    with Session(e["platform"][1]) as session:
        assert reservation_totals(session, provider="anthropic") == (1, Decimal(0))


def test_history_remains_immutable(draft_env):
    from sqlalchemy.exc import DBAPIError

    e = draft_env
    actor, case, token, packet, config = ready(e)
    e["drafts"].request(actor, case, "immutable-dev", packet_request(e), config)
    claim = e["drafts"].claim(token)
    assert e["drafts"].prepare(token, claim) is not None
    with pytest.raises(DBAPIError), e["platform"][1].begin() as connection:
        connection.execute(text("UPDATE investigation_draft_attempts SET input_reservation=1"))
    with Session(e["platform"][1]) as session:
        assert len(session.scalars(select(DraftAttempt)).all()) == 1
