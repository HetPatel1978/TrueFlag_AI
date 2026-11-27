"""Offline protocol tests. These never establish provider compatibility or send data."""

import copy
import json
import runpy
from pathlib import Path

import pytest

from app.schemas.csv_uploads import COLUMNS
from app.schemas.investigation_drafts import ProviderInput
from app.services.claude_contract import MODEL, output_schema, parse_response, request_body
from app.services.csv_validation import validate_row
from app.services.investigation_provider import ProviderFailure


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


def test_wire_schema_requires_fields_to_bound_compilation_complexity(packet):
    def check(value):
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                assert set(value["required"]) == set(value["properties"])
                assert value["additionalProperties"] is False
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    body = json.loads(request_body(packet))
    check(body["output_config"]["format"]["schema"])
    assert body["output_config"]["effort"] == "high"
    assert body["thinking"] == {"type": "between_tools"}


@pytest.fixture
def response():
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


def encoded(value):
    return json.dumps(value).encode()


def test_native_structured_request_is_bounded_and_has_no_tools(packet):
    value = json.loads(request_body(packet))
    assert value["model"] == MODEL
    assert value["output_config"]["format"]["type"] == "json_schema"
    schema = value["output_config"]["format"]["schema"]
    assert schema["properties"]["packet_sha256"] == {"type": "string", "const": "a" * 64}
    for section, expected in (
        ("financial_observations", "calculated_fact"),
        ("unusual_activity", "observed_fact"),
        ("model_signals", "model_signal"),
    ):
        item = schema["properties"][section]["items"]
        item = schema["$defs"][item["$ref"].split("/")[-1]]
        assert item["properties"]["claim_type"] == {"type": "string", "const": expected}
    schema["properties"]["packet_sha256"] = output_schema()["properties"]["packet_sha256"]
    assert schema == output_schema()
    assert "tools" not in value and "stream" not in value
    assert json.loads(value["messages"][0]["content"])["packet_sha256"] == "a" * 64


def test_original_schema_is_enforced_after_wire_decoding(response):
    result = parse_response(encoded(response), max_input_tokens=1000, max_output_tokens=1000)
    assert result.proposal.abstain is True
    assert str(result.estimated_cost_usd) == "0.004"
    proposal = json.loads(response["content"][0]["text"])
    proposal["financial_observations"] = [{}] * 9
    response["content"][0]["text"] = json.dumps(proposal)
    with pytest.raises(ProviderFailure):
        parse_response(encoded(response), max_input_tokens=1000, max_output_tokens=1000)


@pytest.mark.parametrize(
    "change",
    [
        {"model": "unexpected"},
        {"stop_reason": "refusal"},
        {"stop_reason": "max_tokens"},
        {"usage": {}},
        {"usage": {"input_tokens": True, "output_tokens": 1}},
        {"usage": {"input_tokens": 1, "output_tokens": 1001}},
        {"usage": {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 1}},
        {"content": [{"type": "tool_use"}]},
    ],
)
def test_incomplete_unexpected_or_unbounded_response_rejected(response, change):
    value = copy.deepcopy(response)
    value.update(change)
    with pytest.raises(ProviderFailure):
        parse_response(encoded(value), max_input_tokens=1000, max_output_tokens=1000)


def test_scenario_csv_rows_match_canonical_contract_and_manifest():
    path = Path(__file__).resolve().parents[2] / "scripts/create_claude_demo_data.py"
    rows, manifest = runpy.run_path(str(path))["demo_rows"]()
    assert len(rows) == len(manifest) == 5
    seen = set()
    for row, entry in zip(rows, manifest, strict=True):
        cells = ["" if row[column] is None else str(row[column]) for column in COLUMNS]
        assert validate_row(cells, COLUMNS, {name: name for name in COLUMNS}, seen) == ([], [])
        assert row["source_id"] == entry["source_id"]
    assert len(seen) == 5


def test_http_error_diagnostics_never_retain_provider_messages():
    from app.services.claude_contract import http_error_diagnostics

    raw = encoded({"error": {"type": "invalid_request_error", "message": "schema private-value"}})
    result = http_error_diagnostics(raw, "req_allowed123")
    assert result["http_error_type"] == "invalid_request_error"
    assert result["schema_mentioned"] is True
    assert result["request_id"] == "req_allowed123"
    assert "private-value" not in json.dumps(result)
    assert http_error_diagnostics(b"not-json", "untrusted value")["request_id"] is None
