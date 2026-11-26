"""No-network development wire and narrowly scoped financial authorization tests."""

import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.schemas.investigation_drafts import ProviderInput
from app.schemas.provider_live import ClaudeProviderConfig
from app.services.claude_contract import (
    MODEL,
    http_error_diagnostics,
    output_schema,
    parse_response,
    request_body,
)
from app.services.claude_provider import ClaudeProvider, authorize_claude
from app.services.claude_wire_v2 import WireProposal
from app.services.ingestion import digest
from app.services.investigation_provider import ProviderFailure
from app.services.luminal_provider import ProviderRejected


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


@pytest.fixture
def config(packet):
    return ClaudeProviderConfig(
        approval_id="claude-development-review-2026-11-22-v2",
        terms_sha256="b" * 64,
        financial_scope="development_no_spend_cap_v1",
        wire_format="flat_selection_v2",
        max_cost_usd=0,
        purpose="development_validation",
        wire_schema_sha256=digest(output_schema(wire_format="flat_selection_v2")),
        exact_input_sha256=digest(packet.model_dump(mode="json")),
    )


@pytest.fixture
def settings(config):
    return SimpleNamespace(
        anthropic_synthetic_demo_enabled=True,
        anthropic_contract_verified=False,
        anthropic_api_key=SecretStr("offline-secret-key"),
        anthropic_terms_sha256="b" * 64,
        anthropic_demo_call_limit=0,
        anthropic_demo_spend_limit_usd=0,
        anthropic_development_validation_enabled=True,
        anthropic_development_approval_id=config.approval_id,
        anthropic_development_input_sha256=config.exact_input_sha256,
    )


def proposal():
    return dict(
        packet_sha256="a" * 64,
        overview="insufficient_evidence",
        supporting_records=[],
        findings=[],
        hypotheses=[],
        missing_or_contradictory_evidence=[],
        follow_up_questions=[],
        additional_information_needed=[],
        uncertainty_limitations=[],
        next_steps=["human_review"],
        abstain=True,
        uncertainty="requires_human_semantic_review",
    )


def response(document):
    return dict(
        type="message",
        role="assistant",
        model=MODEL,
        stop_reason="end_turn",
        content=[dict(type="text", text=json.dumps(document))],
        usage=dict(input_tokens=500, output_tokens=300),
    )


def test_reference_free_required_schema(packet):
    schema = output_schema(wire_format="flat_selection_v2")
    encoded = json.dumps(schema)
    assert not any(x in encoded for x in ['"$ref"', '"$defs"', '"anyOf"', '"oneOf"', '"default"'])

    def check(v):
        if isinstance(v, dict):
            if v.get("type") == "object":
                assert (
                    set(v["required"]) == set(v["properties"])
                    and v["additionalProperties"] is False
                )
            for c in v.values():
                check(c)
        elif isinstance(v, list):
            for c in v:
                check(c)

    check(schema)
    raw = request_body(packet, wire_format="flat_selection_v2")
    assert json.loads(raw)["max_tokens"] == 4096 and len(raw) < 65536
    assert len(json.dumps(schema)) < len(json.dumps(output_schema()))


def test_explicit_scope_only_skips_obsolete_financial_limits(settings, config):
    authorize_claude(settings, config)
    settings.anthropic_development_validation_enabled = False
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, config)
    settings.anthropic_development_validation_enabled = True
    settings.anthropic_development_input_sha256 = "c" * 64
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, config)


def test_legacy_financial_scope_is_not_disabled(settings):
    old = ClaudeProviderConfig(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="b" * 64,
        max_cost_usd="2.10",
        wire_schema_sha256=digest(output_schema()),
    )
    settings.anthropic_contract_verified = True
    with pytest.raises(ProviderRejected):
        authorize_claude(settings, old)
    settings.anthropic_demo_call_limit = 1
    settings.anthropic_demo_spend_limit_usd = 20
    authorize_claude(settings, old)


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "investigation"},
        {"financial_scope": "reserved_demo_v1"},
        {"max_cost_usd": "2.15"},
        {"wire_format": "legacy_v1"},
        {"max_attempts": 2},
        {"max_output_tokens": 4097},
    ],
)
def test_cannot_widen_development_scope(config, change):
    with pytest.raises(ValidationError):
        ClaudeProviderConfig.model_validate({**config.model_dump(), **change})


def test_real_transport_contract_without_financial_reservation(settings, config, packet):
    calls = []

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield json.dumps(response(proposal())).encode()

    def send(request):
        calls.append(request)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert b"offline-secret-key" not in request.content
        return httpx.Response(200, stream=Stream(), headers={"content-type": "application/json"})

    result = ClaudeProvider(settings, transport=httpx.MockTransport(send)).propose(packet, config)
    assert (
        len(calls) == 1 and result.usage.input_tokens == 500 and result.usage.output_tokens == 300
    )
    assert result.usage.cost_usd == Decimal("0.004")
    assert json.loads(result.content)["overview"] == "insufficient_evidence"


@pytest.mark.parametrize(
    "change",
    [
        {"uncertainty": "certain"},
        {"next_steps": ["close_case"]},
        {"abstain": "false"},
        {"supporting_records": ["forged-reference"]},
        {"unknown_field": True},
        {"regulatory_citations": ["unapproved"]},
    ],
)
def test_local_validation_still_rejects_bad_output(change):
    with pytest.raises(ProviderFailure):
        parse_response(
            json.dumps(response({**proposal(), **change})).encode(),
            max_input_tokens=32768,
            max_output_tokens=4096,
            wire_format="flat_selection_v2",
        )


def test_exact_decimal_and_nullable_metadata():
    value = proposal()
    value["findings"] = [
        dict(
            claim_type="observed_fact",
            reference_id="00000000-0000-0000-0000-000000000001",
            supporting_evidence=[],
            contradictory_evidence=[],
            numeric_statements=[
                dict(
                    metric="amount",
                    value="79.12000001",
                    currency="USD",
                    window_start="",
                    window_end="",
                    feature="",
                )
            ],
        )
    ]
    local = WireProposal.model_validate(value).local_proposal()
    assert local.unusual_activity[0].numeric_statements[0].value == Decimal("79.12000001")
    assert local.unusual_activity[0].numeric_statements[0].window is None
    value["findings"][0]["numeric_statements"][0]["value"] = ""
    with pytest.raises(ValidationError):
        WireProposal.model_validate(value).local_proposal()


def test_development_error_detail_is_bounded_and_credentials_redacted():
    raw = json.dumps(
        dict(
            error=dict(
                type="invalid_request_error",
                message="Schema error offline-secret-key sk-ant-secret\nMore detail",
            )
        )
    ).encode()
    regular = http_error_diagnostics(raw, "req_safe")
    assert "development_error_message" not in regular
    diagnostic = http_error_diagnostics(
        raw, "req_safe", development=True, credential="offline-secret-key"
    )
    assert "offline-secret-key" not in json.dumps(diagnostic) and "sk-ant-secret" not in json.dumps(
        diagnostic
    )
    assert "Schema error" in diagnostic["development_error_message"]


@pytest.mark.parametrize(
    "change",
    [
        {"decision": "pending"},
        {"record_id": "claude-live-validation-review-2026-11-22-v1"},
        {"request_limit": True},
        {"request_limit": 2},
        {"automatic_retries": True},
        {"application_reservation_required": True},
        {"financial_scope": "reserved_demo_v1"},
        {"max_output_tokens": 8192},
        {"general_analyst_activation_authorized": True},
        {"endpoint": "http://api.anthropic.com/v1/messages"},
        {"wire_schema_sha256": "c" * 64},
        {"financial_authorization_sha256": "d" * 64},
    ],
)
def test_new_approval_scope_cannot_reuse_consumed_or_changed_record(
    tmp_path, packet, config, change
):
    import hashlib
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    check = runpy.run_path(str(root / "scripts/validate_claude_live.py"))[
        "approved_development_request"
    ]
    review = tmp_path / "development-v2"
    review.mkdir()
    raw = request_body(packet, wire_format="flat_selection_v2")
    sha = hashlib.sha256(raw).hexdigest()
    (review / "request.json").write_bytes(raw)
    (review / "preflight.json").write_text(json.dumps({"request_sha256": sha}))
    terms = tmp_path / "anthropic_public_terms_snapshot.json"
    terms.write_text("{}")
    record = dict(
        decision="approved",
        record_id="claude-development-review-2026-11-22-v2",
        provider="anthropic",
        model=MODEL,
        endpoint="https://api.anthropic.com/v1/messages",
        financial_scope="development_no_spend_cap_v1",
        wire_format="flat_selection_v2",
        embedded_schema_sha256=digest(json.loads(raw)["output_config"]["format"]["schema"]),
        exact_input_sha256=digest(packet.model_dump(mode="json")),
        provider_terms_sha256=hashlib.sha256(terms.read_bytes()).hexdigest(),
        total_spend_cap_usd=None,
        per_request_spend_cap_usd=None,
        follow_redirects=False,
        tools_enabled=False,
        streaming=False,
        regulatory_grounding_enabled=False,
        request_sha256=sha,
        wire_schema_sha256=config.wire_schema_sha256,
        automatic_retries=False,
        general_analyst_activation_authorized=False,
        application_reservation_required=False,
        financial_authorization_sha256=hashlib.sha256(
            (root / "contracts/claude_development_financial_scope_v1.json").read_bytes()
        ).hexdigest(),
        max_input_tokens=32768,
        max_output_tokens=4096,
        total_token_budget=36864,
        max_request_bytes=65536,
        max_response_bytes=65536,
        request_deadline_seconds=20,
        request_limit=1,
        max_attempts=1,
        max_outstanding_requests=1,
        payload_bytes=len(raw),
    )
    path = review / "owner_approval.json"
    path.write_text(json.dumps(record))
    assert check(tmp_path, config.wire_schema_sha256) == sha
    path.write_text(json.dumps({**record, **change}))
    with pytest.raises(RuntimeError):
        check(tmp_path, config.wire_schema_sha256)
