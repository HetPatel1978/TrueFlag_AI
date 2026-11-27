"""Replay of the recorded real research responses (V8, V10, V12) through the complete
independent verification pipeline, plus a guard that the provider-facing contract keeps
communicating every verifier rule.

Offline only: the evidence packet and research bindings are the recorded synthetic
records those requests were built from; the verifiers are the production code, unchanged.
"""

import json
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

import app.services.research_demo as research_demo
from app.schemas.investigations import InvestigationPacketBody
from app.schemas.research_demo import ResearchBinding, ResearchProviderInput
from app.services import investigation_draft_verifier
from app.services.claude_contract import parse_response, request_body
from app.services.claude_wire_v2 import WIRE_INSTRUCTIONS
from app.services.evidence_read import digest
from app.services.investigation_draft_verifier import (
    DraftVerificationFailure,
    minimize,
    validate_proposal,
)
from app.services.investigation_provider import ProviderFailure
from app.services.investigation_verifier import VerificationFailed
from app.services.research_demo import ResearchEvidenceService

FIXTURES = Path(__file__).parent / "fixtures"
REPLAY = FIXTURES / "research_replay"
RESPONSES = {
    "v8": FIXTURES / "claude_research_v8_response.json",
    "v10": FIXTURES / "claude_research_v10_response.json",
    "v12": REPLAY / "response_v12.json",
}
PACKET_SHA256 = "db8b2babd49c30f057dc11cb216c69952f548da9a1574884e7e30f4c9f33880b"


def packet():
    return InvestigationPacketBody.model_validate_json((REPLAY / "packet.json").read_text())


def binding(version):
    return ResearchBinding.model_validate_json((REPLAY / f"binding_{version}.json").read_text())


def provider_input(version):
    """Exactly the production construction in ResearchEvidenceService.provider_input."""
    values = minimize(packet()).model_dump(exclude={"regulatory_context"})
    bound = binding(version)
    return ResearchProviderInput(
        **values,
        regulatory_binding_sha256=bound.binding_sha256,
        regulatory_passages=bound.passages,
    )


def envelope(version):
    return json.loads(RESPONSES[version].read_text())


def document(value):
    return json.loads(value["content"][0]["text"])


def encode(value, doc):
    value = deepcopy(value)
    value["content"][0]["text"] = json.dumps(doc)
    return json.dumps(value).encode()


def verify(version, raw, monkeypatch):
    """parse -> independent financial/evidence verifier -> research citation verifier."""
    proposal = parse_response(
        raw, max_input_tokens=32768, max_output_tokens=4096, grounded=True,
        wire_format="flat_selection_v2",
    ).proposal
    bound, evidence = binding(version), packet()
    service = object.__new__(ResearchEvidenceService)
    # Only the database/clock re-read and the audit write are replaced; the recorded
    # binding is the one the request was built from. Every proposal check is production code.
    service._revalidate = lambda session, actor, b: evidence
    monkeypatch.setattr(research_demo, "audit", lambda *args, **kwargs: None)
    cited = ResearchEvidenceService.verify.__wrapped__(service, None, bound.actor_id, bound, proposal)
    return proposal, cited


def permitted():
    return {str(e.record_version_id) for e in packet().evidence}


def fact_ids():
    return {str(f.reference_id) for f in packet().facts}


def correct_v10(doc):
    doc = deepcopy(doc)
    doc["additional_information_needed"] = []
    return doc


def correct_v12(doc):
    doc = deepcopy(doc)
    ok = permitted()
    doc["supporting_records"] = [r for r in doc["supporting_records"] if r in ok]
    for hypothesis in doc["hypotheses"]:
        hypothesis["supporting_evidence"] = [r for r in hypothesis["supporting_evidence"] if r in ok]
    return doc


def correct_v8(doc):
    from test_claude_wire_contract import compliant  # the existing V8 schema correction

    doc = correct_v12(compliant(doc))
    for finding in doc["findings"]:
        if finding["claim_type"] == "calculated_fact":
            for number in finding["numeric_statements"]:
                number["currency"] = "USD"  # V8 left observed_count without the fact's currency
    doc["follow_up_questions"] = [q for q in doc["follow_up_questions"] if q in packet().questions]
    doc["additional_information_needed"] = [
        q for q in doc["additional_information_needed"] if q in packet().questions
    ]
    return doc


def test_recorded_packet_is_the_one_every_request_was_built_from():
    evidence = packet()
    assert digest(evidence.model_dump(mode="json")) == PACKET_SHA256
    for version in RESPONSES:
        assert binding(version).packet_sha256 == PACKET_SHA256
        assert minimize(evidence).packet_sha256 == document(envelope(version))["packet_sha256"]
    recorded = json.loads(
        (FIXTURES / "research_replay" / "binding_v12.json").read_text()
    )["binding_sha256"]
    assert document(envelope("v12"))["regulatory_binding_sha256"] == recorded


def test_original_v8_output_remains_rejected():
    with pytest.raises(ProviderFailure):
        parse_response(
            RESPONSES["v8"].read_bytes(), max_input_tokens=32768, max_output_tokens=4096,
            grounded=True, wire_format="flat_selection_v2",
        )


@pytest.mark.parametrize(
    "version, reason", [("v10", "question_mismatch"), ("v12", "supporting_reference_invalid")]
)
def test_original_v10_and_v12_outputs_remain_rejected(version, reason, monkeypatch):
    with pytest.raises(DraftVerificationFailure) as error:
        verify(version, RESPONSES[version].read_bytes(), monkeypatch)
    assert error.value.reason == reason


@pytest.mark.parametrize(
    "version, correct", [("v8", correct_v8), ("v10", correct_v10), ("v12", correct_v12)]
)
def test_minimally_corrected_outputs_pass_the_complete_pipeline(version, correct, monkeypatch):
    value = envelope(version)
    proposal, cited = verify(version, encode(value, correct(document(value))), monkeypatch)
    assert {str(c.reference_id) for c in cited} == {
        str(p.reference_id) for p in binding(version).passages
    }
    totals = {
        (n.metric, n.value)
        for f in proposal.financial_observations
        for n in f.numeric_statements
    }
    assert ("observed_total", Decimal("10020.00000000")) in totals
    assert ("observed_count", Decimal("12")) in totals


def corrected_v12():
    value = envelope("v12")
    return value, correct_v12(document(value))


@pytest.mark.parametrize(
    "change, reason",
    [
        ("fabricated_total", "numeric_value_mismatch"),
        ("fabricated_count", "numeric_value_mismatch"),
        ("wrong_currency", "numeric_value_mismatch"),
        ("fabricated_shap", "numeric_value_mismatch"),
        ("unknown_supporting_record", "supporting_reference_invalid"),
        ("fact_id_in_supporting_records", "supporting_reference_invalid"),
        ("fact_id_in_hypothesis", "hypothesis_reference_invalid"),
        ("fact_id_in_finding_evidence", "reference_not_authorized"),
        ("unknown_reference_id", "calculation_reference_mismatch"),
        ("duplicate_finding", "duplicate_finding"),
    ],
)
def test_fabricated_financial_and_reference_content_is_rejected(change, reason, monkeypatch):
    value, doc = corrected_v12()
    calc = next(f for f in doc["findings"] if f["claim_type"] == "calculated_fact")
    model = next(f for f in doc["findings"] if f["claim_type"] == "model_signal")
    fact = sorted(fact_ids())[0]
    if change == "fabricated_total":
        calc["numeric_statements"][0]["value"] = "10021.00000000"
    if change == "fabricated_count":
        calc["numeric_statements"][1]["value"] = "13"
    if change == "wrong_currency":
        calc["numeric_statements"][0]["currency"] = "EUR"
    if change == "fabricated_shap":
        model["numeric_statements"][2]["value"] = "0.9"
    if change == "unknown_supporting_record":
        doc["supporting_records"].append("00000000-0000-4000-8000-000000000000")
    if change == "fact_id_in_supporting_records":
        doc["supporting_records"].append(fact)
    if change == "fact_id_in_hypothesis":
        doc["hypotheses"][0]["supporting_evidence"].append(fact)
    if change == "fact_id_in_finding_evidence":
        calc["contradictory_evidence"] = [fact]
    if change == "unknown_reference_id":
        calc["reference_id"] = "00000000-0000-4000-8000-000000000000"
    if change == "duplicate_finding":
        doc["findings"].append(deepcopy(calc))
    with pytest.raises(DraftVerificationFailure) as error:
        verify("v12", encode(value, doc), monkeypatch)
    assert error.value.reason == reason


@pytest.mark.parametrize("change", ["unknown_citation", "no_citation", "duplicate", "other_binding"])
def test_unsupported_citations_are_rejected(change, monkeypatch):
    value, doc = corrected_v12()
    if change == "unknown_citation":
        doc["regulatory_citations"] = ["00000000-0000-4000-8000-000000000000"]
    if change == "no_citation":
        doc["regulatory_citations"] = []
    if change == "duplicate":
        doc["regulatory_citations"] = doc["regulatory_citations"][:1] * 2
    if change == "other_binding":
        doc["regulatory_binding_sha256"] = binding("v10").binding_sha256
    with pytest.raises(VerificationFailed, match="research_citation_invalid"):
        verify("v12", encode(value, doc), monkeypatch)


# ---- provider-facing contract alignment -------------------------------------------------


def schema_errors(schema, value, path="$"):
    """The JSON-schema subset the provider format uses (type/enum/const/properties/items)."""
    errors = []
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool}
    if kind in types and not isinstance(value, types[kind]):
        return [f"{path}: type"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum")
    if kind == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, item in value.items():
            if key not in properties:
                if schema.get("additionalProperties") is False:
                    errors.append(f"{path}.{key}: additional")
                continue
            errors += schema_errors(properties[key], item, f"{path}.{key}")
    if kind == "array":
        for index, item in enumerate(value):
            errors += schema_errors(schema.get("items", {}), item, f"{path}[{index}]")
    return errors


def provider_request(version="v12"):
    return json.loads(request_body(provider_input(version), wire_format="flat_selection_v2"))


def test_every_evidence_and_reference_field_is_restricted_to_supplied_identifiers():
    sent = provider_input("v12")
    props = provider_request()["output_config"]["format"]["schema"]["properties"]
    evidence = [str(r) for r in sent.evidence_references]
    assert props["supporting_records"]["items"]["enum"] == evidence
    for section in ("findings", "hypotheses"):
        for field in ("supporting_evidence", "contradictory_evidence"):
            assert props[section]["items"]["properties"][field]["items"]["enum"] == evidence
    references = props["findings"]["items"]["properties"]["reference_id"]["enum"]
    assert set(references) == (
        {str(t["reference_id"]) for t in sent.transactions}
        | {str(f["reference_id"]) for f in sent.financial_facts}
        | {str(sent.model_signal["assessment_id"])}
    )
    assert not fact_ids() & set(evidence)  # calculation IDs only as a finding reference_id
    assert props["regulatory_citations"]["items"]["enum"] == [
        str(p.reference_id) for p in sent.regulatory_passages
    ]
    for field in ("follow_up_questions", "additional_information_needed"):
        assert props[field]["items"]["enum"] == list(sent.questions)


def test_provider_schema_would_have_blocked_the_recorded_defects_but_accepts_corrections():
    schema = provider_request()["output_config"]["format"]["schema"]
    v12 = document(envelope("v12"))
    errors = schema_errors(schema, v12)
    assert any(e.startswith("$.supporting_records") for e in errors)
    assert any(e.startswith("$.hypotheses") for e in errors)
    assert schema_errors(schema, document(envelope("v10")))  # missing-evidence codes
    for version, correct in (("v8", correct_v8), ("v10", correct_v10), ("v12", correct_v12)):
        doc = correct(document(envelope(version)))
        doc["regulatory_binding_sha256"] = schema["properties"]["regulatory_binding_sha256"]["const"]
        doc["regulatory_citations"] = [
            c for c in doc["regulatory_citations"]
            if c in schema["properties"]["regulatory_citations"]["items"]["enum"]
        ]
        assert schema_errors(schema, doc) == [], version


def verifier_reasons():
    source = Path(investigation_draft_verifier.__file__).read_text()
    return set(re.findall(r'DraftVerificationFailure\("([a-z_]+)"\)', source))


# Every independent verifier rule, and where the provider is told about it.
CONTRACT_CHECKLIST = {
    "supporting_reference_invalid": ["schema:supporting_records", "never a financial_fact"],
    "missing_evidence_mismatch": ["Copy missing_or_contradictory_evidence"],
    "limitations_mismatch": ["uncertainty_limitations exactly"],
    "claim_type_mismatch": ["schema:claim_type"],
    "overview_mismatch": ["overview to insufficient_evidence", "requires non-empty supporting_records"],
    "packet_hash_mismatch": ["schema:packet_sha256"],
    "question_mismatch": ["schema:questions", "each at most once"],
    "duplicate_finding": ["reference_id pair appears at most once"],
    "reference_not_authorized": ["schema:finding_evidence"],
    "transaction_reference_mismatch": ["observed_fact uses a supplied transaction reference_id",
                                       "exactly its own transaction reference_id"],
    "calculation_reference_mismatch": ["calculated_fact uses a supplied financial_fact reference_id",
                                       "supporting_evidence equal to its input_record_ids"],
    "model_signal_mismatch": ["model_signal uses the supplied model_signal assessment_id",
                              "has empty supporting_evidence"],
    "numeric_feature_mismatch": ["feature is empty except for shap_contribution"],
    "numeric_value_mismatch": ["exact decimal strings", "with that fact's currency and window",
                               "(also for observed_count)",
                               "with that transaction's currency and an empty window",
                               "empty currency and window"],
    "hypothesis_reference_invalid": ["schema:hypothesis_evidence", "each question_code at most once"],
    "conflicts_hypothesis_unsupported": ["resolve_conflicting_observations (only when conflicts"],
    "coverage_hypothesis_unsupported": ["coverage_gap_requires_more_evidence (only when missing"],
    "concentration_hypothesis_unsupported": ["review_observed_concentration (requires supporting"],
    "abstention_required": ["set abstain to true"],
    "conflict_step_unsupported": ["resolve_conflicts (only when conflicts are supplied)"],
}


def test_every_verifier_rule_is_communicated_to_the_provider():
    # A new verifier rule fails here until the provider contract states it.
    assert verifier_reasons() == set(CONTRACT_CHECKLIST)
    request = provider_request()
    system = request["system"]
    props = request["output_config"]["format"]["schema"]["properties"]
    finding = props["findings"]["items"]["properties"]
    hypothesis = props["hypotheses"]["items"]["properties"]
    schema_checks = {
        "schema:supporting_records": "enum" in props["supporting_records"]["items"],
        "schema:claim_type": set(finding["claim_type"]["enum"])
        == {"observed_fact", "calculated_fact", "model_signal"},
        "schema:packet_sha256": "const" in props["packet_sha256"],
        "schema:questions": all(
            "enum" in props[f]["items"] for f in ("follow_up_questions", "additional_information_needed")
        ),
        "schema:finding_evidence": all(
            "enum" in finding[f]["items"] for f in ("supporting_evidence", "contradictory_evidence")
        ),
        "schema:hypothesis_evidence": all(
            "enum" in hypothesis[f]["items"] for f in ("supporting_evidence", "contradictory_evidence")
        ),
    }
    for reason, requirements in CONTRACT_CHECKLIST.items():
        for requirement in requirements:
            if requirement.startswith("schema:"):
                assert schema_checks[requirement], (reason, requirement)
            else:
                assert requirement in system, (reason, requirement)
    # Research citation verifier (research_demo.verify): binding const, non-empty, unique, supplied.
    assert "const" in props["regulatory_binding_sha256"]
    assert "enum" in props["regulatory_citations"]["items"]
    assert "at least one supplied passage reference_id, each at most once" in system
    assert "UNAPPROVED" in system


def test_instructions_cover_local_schema_limits():
    for phrase in ("no more than 5 numeric_statements", "at most 8", "1 model_signal"):
        assert phrase in WIRE_INSTRUCTIONS
    assert UUID(provider_request()["output_config"]["format"]["schema"]["properties"]
                ["findings"]["items"]["properties"]["reference_id"]["enum"][0])


# ---- flat_selection_v3: per-finding regulatory citations ------------------------------------


def v3_doc(links):
    value, doc = corrected_v12()
    doc = deepcopy(doc)
    doc["finding_citations"] = links
    return value, doc


def verify_v3(raw, monkeypatch):
    proposal = parse_response(
        raw, max_input_tokens=32768, max_output_tokens=4096, grounded=True,
        wire_format="flat_selection_v3",
    ).proposal
    bound, evidence = binding("v12"), packet()
    service = object.__new__(ResearchEvidenceService)
    service._revalidate = lambda session, actor, b: evidence
    monkeypatch.setattr(research_demo, "audit", lambda *args, **kwargs: None)
    return proposal, ResearchEvidenceService.verify.__wrapped__(
        service, None, bound.actor_id, bound, proposal
    )


def first_link():
    _, doc = corrected_v12()
    finding = next(f for f in doc["findings"] if f["claim_type"] == "calculated_fact")
    return finding["reference_id"], doc["regulatory_citations"][0]


def test_v3_finding_citations_inside_the_retrieved_set_pass(monkeypatch):
    finding, source = first_link()
    value, doc = v3_doc([{"finding_reference_id": finding, "regulatory_citation": source}])
    proposal, cited = verify_v3(encode(value, doc), monkeypatch)
    assert [(str(l.finding_reference_id), str(l.regulatory_citation)) for l in proposal.finding_citations] == [
        (finding, source)
    ]
    assert cited


@pytest.mark.parametrize("change", ["outside_retrieved_set", "unknown_finding", "not_cited", "duplicate"])
def test_v3_verifier_rejects_a_finding_citation_outside_the_retrieved_set(change, monkeypatch):
    finding, source = first_link()
    link = {"finding_reference_id": finding, "regulatory_citation": source}
    links = [link]
    value, doc = v3_doc(links)
    if change == "outside_retrieved_set":
        link["regulatory_citation"] = "00000000-0000-4000-8000-000000000000"
    if change == "unknown_finding":
        link["finding_reference_id"] = "00000000-0000-4000-8000-000000000001"
    if change == "not_cited":
        others = [str(p.reference_id) for p in binding("v12").passages if str(p.reference_id) != source]
        doc["regulatory_citations"] = [source]
        link["regulatory_citation"] = others[0]
    if change == "duplicate":
        doc["finding_citations"] = [link, dict(link)]
    with pytest.raises(VerificationFailed) as error:
        verify_v3(encode(value, doc), monkeypatch)
    # The reason is recorded in the verification result (an allowed, fixed code).
    assert error.value.reason == "research_finding_citation_invalid"
    from app.services.investigation_drafts import VERIFICATION_REASONS

    assert error.value.reason in VERIFICATION_REASONS


def test_v3_provider_schema_restricts_links_to_returned_findings_and_retrieved_sources():
    body = json.loads(
        request_body(provider_input("v12"), max_output_tokens=4096, max_bytes=65536,
                     wire_format="flat_selection_v3")
    )
    schema = body["output_config"]["format"]["schema"]
    link = schema["properties"]["finding_citations"]["items"]["properties"]
    assert set(link["regulatory_citation"]["enum"]) == {
        str(p.reference_id) for p in binding("v12").passages
    }
    assert set(link["finding_reference_id"]["enum"]) == set(
        schema["properties"]["findings"]["items"]["properties"]["reference_id"]["enum"]
    )
    assert "finding_citations" in body["system"]


def test_v2_requests_are_unchanged_by_v3():
    body = json.loads(
        request_body(provider_input("v12"), max_output_tokens=4096, max_bytes=65536,
                     wire_format="flat_selection_v2")
    )
    assert "finding_citations" not in body["output_config"]["format"]["schema"]["properties"]
    assert "finding_citations" not in body["system"]
