"""Provider-facing flat_selection_v2 schema must agree with TrueFlag's local contract.

Offline only. The fixture is the recorded V8 research response (synthetic data); it was
rejected locally because the wire schema/instructions were looser than AIProposal.
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import get_args

import pytest

from app.schemas.investigation_drafts import NumericStatement, ProposedHypothesis
from app.schemas.provider_live import AIProposal
from app.schemas.regulatory_investigation import GroundedAIProposal
from app.services.claude_contract import parse_response, response_diagnostics
from app.services.claude_wire_v2 import WIRE_INSTRUCTIONS, wire_schema
from app.services.investigation_provider import ProviderFailure

FIXTURE = Path(__file__).parent / "fixtures" / "claude_research_v8_response.json"


def envelope():
    return json.loads(FIXTURE.read_text())


def document(value):
    return json.loads(value["content"][0]["text"])


def encode(value, doc):
    value = deepcopy(value)
    value["content"][0]["text"] = json.dumps(doc)
    return json.dumps(value).encode()


def parse(raw):
    return parse_response(
        raw, max_input_tokens=32768, max_output_tokens=4096, grounded=True,
        wire_format="flat_selection_v2",
    )


def compliant(doc):
    """The V8 answer corrected only where it broke the (now explicit) contract."""
    doc = deepcopy(doc)
    for finding in doc["findings"]:
        if finding["claim_type"] == "calculated_fact":
            finding["numeric_statements"] = [
                n for n in finding["numeric_statements"]
                if n["metric"] in ("observed_total", "observed_count")
            ][:5]
        elif finding["claim_type"] == "model_signal":
            finding["supporting_evidence"] = []
            for n in finding["numeric_statements"]:
                if n["metric"] == "model_score":
                    n["metric"] = "score"
            finding["numeric_statements"] = finding["numeric_statements"][:5]
    doc["hypotheses"] = [
        {**doc["hypotheses"][0], "question_code": "coverage_gap_requires_more_evidence"}
    ]
    doc["next_steps"] = ["collect_missing_evidence", "human_review"]
    return doc


def enum_at(schema, *path):
    node = schema
    for key in path:
        node = node[key]
    return node.get("enum") or [node["const"]]


def test_provider_schema_enums_match_local_contract():
    schema = wire_schema(grounded=True)
    props = schema["properties"]
    finding = props["findings"]["items"]
    assert set(enum_at(finding, "properties", "numeric_statements", "items", "properties", "metric")) == set(
        get_args(NumericStatement.model_fields["metric"].annotation)
    )
    assert set(enum_at(props["hypotheses"]["items"], "properties", "question_code")) == set(
        get_args(ProposedHypothesis.model_fields["question_code"].annotation)
    )
    local_steps = get_args(get_args(AIProposal.model_fields["next_steps"].annotation)[0])
    assert set(enum_at(props["next_steps"], "items")) == set(local_steps)
    # Every other existing enum remains carried to the provider.
    assert set(enum_at(finding, "properties", "claim_type")) == {
        "observed_fact", "calculated_fact", "model_signal"
    }
    assert set(enum_at(props, "overview")) == set(
        get_args(AIProposal.model_fields["overview"].annotation)
    )
    assert enum_at(props, "uncertainty") == ["requires_human_semantic_review"]
    assert enum_at(props["hypotheses"]["items"], "properties", "uncertainty") == [
        "unconfirmed_requires_human_review"
    ]


def test_instructions_state_limits_and_no_longer_misdirect_hypothesis_codes():
    assert "no more than 5 numeric_statements" in WIRE_INSTRUCTIONS
    assert "Select question codes only from supplied questions" not in WIRE_INSTRUCTIONS
    assert "question_code is not taken from the supplied questions" in WIRE_INSTRUCTIONS
    for code in ("review_observed_concentration", "human_review", "shap_contribution"):
        assert code in WIRE_INSTRUCTIONS


def test_recorded_v8_response_remains_rejected():
    raw = FIXTURE.read_bytes()
    with pytest.raises(ProviderFailure, match="provider_invalid_response"):
        parse(raw)
    diagnostics = response_diagnostics(raw, wire_format="flat_selection_v2", grounded=True)
    assert diagnostics["parseable"] is True and diagnostics["stop_reason"] == "end_turn"
    assert diagnostics["schema_valid"] is False and diagnostics["schema_errors"]


def test_contract_compliant_response_passes_schema_validation():
    value = envelope()
    result = parse(encode(value, compliant(document(value))))
    proposal = result.proposal
    assert isinstance(proposal, GroundedAIProposal)
    assert proposal.next_steps == ["collect_missing_evidence", "human_review"]
    assert all(len(f.numeric_statements) <= 5 for f in proposal.financial_observations)
    assert proposal.model_signals[0].numeric_statements[0].metric == "score"
    assert result.input_tokens == 11684 and result.output_tokens == 3425


@pytest.mark.parametrize(
    "change",
    ["six_numbers", "free_text_step", "unknown_metric", "question_as_hypothesis"],
)
def test_each_original_contract_break_is_still_rejected(change):
    value = envelope()
    doc = compliant(document(value))
    calc = next(f for f in doc["findings"] if f["claim_type"] == "calculated_fact")
    if change == "six_numbers":
        calc["numeric_statements"] = calc["numeric_statements"][:1] * 6
    if change == "free_text_step":
        doc["next_steps"] = ["Human reviewer to examine the supplied source observations"]
    if change == "unknown_metric":
        calc["numeric_statements"][0]["metric"] = "incoming_total"
    if change == "question_as_hypothesis":
        doc["hypotheses"][0]["question_code"] = "review_authorized_source_observations"
    with pytest.raises(ProviderFailure):
        parse(encode(value, doc))


def test_recorded_v10_response_meets_the_aligned_format():
    """V10 (after the enum fix) parsed cleanly; it failed only the independent verifier."""
    raw = (Path(__file__).parent / "fixtures" / "claude_research_v10_response.json").read_bytes()
    proposal = parse(raw).proposal
    assert proposal.next_steps == ["collect_missing_evidence", "review_model_alignment", "human_review"]
    assert all(len(f.numeric_statements) <= 5 for f in proposal.financial_observations)
    # The remaining V10 defect: missing-evidence codes where only question codes are allowed.
    assert "comparable_expected_activity" in proposal.additional_information_needed
