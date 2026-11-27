"""Offline compact regulatory wire checks; no approval or provider activation."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_claude_development import proposal, response

from app.schemas.provider_live import ClaudeProviderConfig, GroundedClaudeConfig
from app.schemas.regulatory_investigation import GroundedAIProposal
from app.services.claude_contract import output_schema, parse_response, response_diagnostics
from app.services.ingestion import digest
from app.services.investigation_provider import ProviderFailure


def document():
    return {
        **proposal(),
        "regulatory_binding_sha256": "b" * 64,
        "regulatory_citations": [str(uuid4())],
    }


def parse(value, *, grounded=True):
    return parse_response(
        json.dumps(response(value)).encode(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        grounded=grounded,
        wire_format="flat_selection_v2",
    ).proposal


def test_compact_grounding_projects_into_existing_strict_local_contract():
    value = document()
    parsed = parse(value)
    assert isinstance(parsed, GroundedAIProposal)
    assert parsed.regulatory_binding_sha256 == value["regulatory_binding_sha256"]
    assert [str(v) for v in parsed.regulatory_citations] == value["regulatory_citations"]
    assert parsed.abstain and parsed.uncertainty == "requires_human_semantic_review"
    assert response_diagnostics(
        json.dumps(response(value)).encode(), wire_format="flat_selection_v2", grounded=True
    )["schema_valid"]


def test_compact_grounding_schema_is_closed_and_reference_free():
    schema = output_schema(grounded=True, wire_format="flat_selection_v2")
    assert {"regulatory_binding_sha256", "regulatory_citations"} <= set(schema["required"])
    assert not any(key in json.dumps(schema) for key in ['"$ref"', '"$defs"', '"anyOf"'])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "update",
    [
        {"regulatory_binding_sha256": "forged"},
        {"regulatory_citations": ["not-a-reference"]},
        {"regulatory_citations": [str(uuid4()) for _ in range(6)]},
        {"abstain": "true"},
        {"next_steps": ["automatically_file_sar"]},
        {"unsupported_legal_conclusion": "a filing is mandatory"},
    ],
)
def test_invalid_grounded_selections_still_fail_local_validation(update):
    with pytest.raises(ProviderFailure):
        parse({**document(), **update})


def test_ungrounded_approval_contract_cannot_accept_added_regulatory_content():
    with pytest.raises(ProviderFailure):
        parse(document(), grounded=False)


def test_missing_grounding_cannot_be_presented_as_grounded_response():
    with pytest.raises(ProviderFailure):
        parse(proposal())


def test_compact_grounded_configuration_preserves_existing_financial_and_scope_checks():
    values = dict(
        approval_id="synthetic-claude-demo-2026-11-20",
        terms_sha256="a" * 64,
        wire_format="flat_selection_v2",
        wire_schema_sha256=digest(output_schema(grounded=True, wire_format="flat_selection_v2")),
        max_cost_usd="2.10",
    )
    GroundedClaudeConfig(**values, regulatory_binding_sha256="b" * 64)
    with pytest.raises(ValidationError):
        GroundedClaudeConfig(**{**values, "max_cost_usd": "0"}, regulatory_binding_sha256="b" * 64)
    with pytest.raises(ValidationError):
        ClaudeProviderConfig(**values)  # Ordinary ungrounded activation is not widened.
