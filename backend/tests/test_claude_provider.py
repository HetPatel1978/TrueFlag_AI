"""No-network tests for the separately gated Claude candidate."""

import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.schemas.investigation_drafts import ProviderInput, ProviderReply
from app.schemas.provider_live import ClaudeProviderConfig, configuration
from app.services.claude_contract import MODEL, output_schema
from app.services.claude_provider import ClaudeProvider
from app.services.ingestion import digest
from app.services.investigation_provider import ProviderFailure
from app.services.luminal_provider import ProviderRateLimited, ProviderRejected


@pytest.fixture
def config():
    return ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_schema_sha256=digest(output_schema()),
        max_cost_usd=Decimal("2.10"),
    )


@pytest.fixture
def settings():
    return SimpleNamespace(
        anthropic_synthetic_demo_enabled=True,
        anthropic_contract_verified=True,
        anthropic_terms_sha256="a" * 64,
        anthropic_api_key=SecretStr("offline-test-key"),
        anthropic_demo_call_limit=5,
        anthropic_demo_spend_limit_usd=20,
    )


@pytest.fixture
def packet():
    return ProviderInput(
        packet_sha256="a" * 64,
        evidence_requires_abstention=True,
        transactions=[],
        financial_facts=[],
        model_signal=None,
        missing_evidence=[],
        conflicts=[],
        limitations=[],
        questions=[],
        evidence_references=[],
    )


def valid_response():
    proposal = {
        "packet_sha256": "a" * 64,
        "overview": "insufficient_evidence",
        "supporting_records": [],
        "financial_observations": [],
        "unusual_activity": [],
        "model_signals": [],
        "risk_indicators": [],
        "missing_or_contradictory_evidence": [],
        "follow_up_questions": [],
        "additional_information_needed": [],
        "uncertainty_limitations": [],
        "next_steps": ["human_review"],
        "abstain": True,
        "uncertainty": "requires_human_semantic_review",
    }
    return {
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(proposal)}],
        "usage": {"input_tokens": 500, "output_tokens": 300},
    }


def test_live_validation_requires_exact_operator_authority(settings, config, packet):
    from app.services.claude_provider import authorize_claude

    exact = digest(packet.model_dump(mode="json"))
    candidate = config.model_copy(
        update={"purpose": "live_validation", "exact_input_sha256": exact}
    )
    settings.anthropic_contract_verified = False
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, candidate)
    settings.anthropic_live_validation_enabled = True
    settings.anthropic_live_validation_input_sha256 = "b" * 64
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, candidate)
    settings.anthropic_live_validation_input_sha256 = exact
    authorize_claude(settings, candidate)
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, config)


def test_fixed_host_and_valid_response(settings, config, packet):
    calls = []

    class ResponseStream(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps(valid_response()).encode()

    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "offline-test-key"
        assert json.loads(request.content)["output_config"]["format"]["type"] == "json_schema"
        return httpx.Response(
            200, stream=ResponseStream(), headers={"content-type": "application/json"}
        )

    reply = ClaudeProvider(settings, transport=httpx.MockTransport(handler)).propose(packet, config)
    assert len(calls) == 1
    assert reply.provider == "anthropic" and reply.model == MODEL
    assert reply.usage.cost_usd == Decimal("0.004")
    assert ProviderReply.model_validate_json(reply.model_dump_json()) == reply
    assert configuration(config.model_dump(mode="json")) == config


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("anthropic_synthetic_demo_enabled", False),
        ("anthropic_contract_verified", False),
        ("anthropic_terms_sha256", "b" * 64),
        ("anthropic_api_key", SecretStr("")),
        ("anthropic_demo_spend_limit_usd", 21),
        ("anthropic_demo_call_limit", 0),
    ],
)
def test_disabled_or_unapproved_request_never_reaches_transport(
    settings, config, packet, attribute, value
):
    setattr(settings, attribute, value)
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request))
    with pytest.raises(ProviderRejected):
        ClaudeProvider(settings, transport=transport).propose(packet, config)
    assert calls == []


@pytest.mark.parametrize("status", [401, 400, 500, 429])
def test_http_failures_are_terminal_and_not_retried(settings, config, packet, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="untrusted provider details")

    with pytest.raises(ProviderRateLimited if status == 429 else ProviderRejected):
        ClaudeProvider(settings, transport=httpx.MockTransport(handler)).propose(packet, config)
    assert len(calls) == 1


def test_timeout_is_not_retried(settings, config, packet):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("sensitive details")

    with pytest.raises(ProviderFailure, match="provider_timeout"):
        ClaudeProvider(settings, transport=httpx.MockTransport(handler)).propose(packet, config)
    assert len(calls) == 1


def test_http_error_records_allowlisted_diagnostics_without_response_text(settings, config, packet):
    class ErrorStream(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps(
                {"error": {"type": "invalid_request_error", "message": "schema private-value"}}
            ).encode()

    calls = []

    def receive(request):
        calls.append(request)
        return httpx.Response(400, headers={"request-id": "req_fixture"}, stream=ErrorStream())

    with pytest.raises(ProviderRejected) as result:
        ClaudeProvider(settings, transport=httpx.MockTransport(receive)).propose(packet, config)
    assert len(calls) == 1
    assert result.value.http_status == 400
    assert result.value.diagnostics["http_error_type"] == "invalid_request_error"
    assert result.value.diagnostics["schema_mentioned"] is True
    assert "private-value" not in json.dumps(result.value.diagnostics)


def test_invalid_provider_output_records_only_bounded_diagnostics(settings, config, packet):
    response = valid_response()
    response["stop_reason"] = "max_tokens"
    response["content"][0]["text"] = "private synthetic response"

    class ResponseStream(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps(response).encode()

    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, stream=ResponseStream(), headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(ProviderRejected) as failure:
        ClaudeProvider(settings, transport=transport).propose(packet, config)
    details = failure.value.diagnostics
    assert failure.value.http_status == 200
    assert details["stop_reason"] == "max_tokens" and details["schema_valid"] is False
    assert details["input_tokens"] == 500 and details["output_tokens"] == 300
    assert "private synthetic response" not in json.dumps(details)


def test_schema_diagnostics_identify_field_without_leaking_invalid_value(settings, config, packet):
    response = valid_response()
    proposal = json.loads(response["content"][0]["text"])
    proposal["follow_up_questions"] = ["SECRET CUSTOMER VALUE"]
    response["content"][0]["text"] = json.dumps(proposal)

    class ResponseStream(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps(response).encode()

    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, stream=ResponseStream(), headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(ProviderRejected) as failure:
        ClaudeProvider(settings, transport=transport).propose(packet, config)
    assert failure.value.diagnostics["schema_errors"] == [
        "follow_up_questions:string_pattern_mismatch"
    ]
    assert "SECRET" not in json.dumps(failure.value.diagnostics)


def test_bootstrap_accepts_only_exact_packet_without_preverified_contract(settings, config, packet):
    settings.anthropic_contract_verified = False
    settings.anthropic_bootstrap_enabled = True
    settings.anthropic_bootstrap_input_sha256 = digest(packet.model_dump(mode="json"))
    probe = ClaudeProviderConfig.model_validate(
        {
            **config.model_dump(),
            "purpose": "compatibility_probe",
            "exact_input_sha256": settings.anthropic_bootstrap_input_sha256,
        }
    )
    modified = packet.model_copy(update={"packet_sha256": "b" * 64})
    calls = []
    provider = ClaudeProvider(settings, transport=httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(ProviderRejected, match="synthetic_probe_input_mismatch"):
        provider.propose(modified, probe)
    assert calls == []
    with pytest.raises(ProviderRejected):
        provider.propose(packet, config)
    assert calls == []


def test_conservative_reservation_and_identity_cannot_be_weakened(config):
    for change in [
        {"max_cost_usd": "2.09"},
        {"max_output_tokens": 4097},
        {"input_usd_per_million": "1"},
        {"max_attempts": 2},
        {"base_url": "https://example.com"},
    ]:
        with pytest.raises(ValidationError):
            ClaudeProviderConfig.model_validate({**config.model_dump(), **change})
    with pytest.raises(ValidationError):
        ProviderReply(
            provider="anthropic",
            model="deepseek-ai/DeepSeek-V4.1-Flash",
            content="{}",
            finish_reason="complete",
            usage={
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0,
                "basis": "provider_reported_tokens_configured_rate_estimate",
            },
        )
