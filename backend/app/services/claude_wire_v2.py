"""Small, reference-free wire format; original AIProposal remains the local contract."""

from copy import deepcopy
from typing import Literal

from pydantic import Field

from app.schemas.evidence_read import Contract
from app.schemas.provider_live import AIProposal

WIRE_FORMAT = "flat_selection_v2"


class WireNumber(Contract):
    # Same accepted values as the local NumericStatement contract; the provider-facing
    # schema now carries them as an enum instead of an unconstrained string.
    metric: Literal[
        "amount", "observed_total", "observed_count", "score", "shap_base", "shap_contribution"
    ]
    value: str
    currency: str
    window_start: str
    window_end: str
    feature: str


class WireFinding(Contract):
    claim_type: Literal["observed_fact", "calculated_fact", "model_signal"]
    reference_id: str
    supporting_evidence: list[str]
    contradictory_evidence: list[str]
    numeric_statements: list[WireNumber]


class WireHypothesis(Contract):
    # Same accepted values as the local ProposedHypothesis contract.
    question_code: Literal[
        "review_observed_concentration",
        "coverage_gap_requires_more_evidence",
        "resolve_conflicting_observations",
    ]
    supporting_evidence: list[str]
    contradictory_evidence: list[str]
    uncertainty: Literal["unconfirmed_requires_human_review"]


class WireProposal(Contract):
    packet_sha256: str
    overview: Literal["review_supplied_evidence", "insufficient_evidence"]
    supporting_records: list[str]
    findings: list[WireFinding] = Field(max_length=17)
    hypotheses: list[WireHypothesis] = Field(max_length=8)
    missing_or_contradictory_evidence: list[str]
    follow_up_questions: list[str]
    additional_information_needed: list[str]
    uncertainty_limitations: list[str]
    # Same accepted values as the local AIProposal contract.
    next_steps: list[
        Literal["collect_missing_evidence", "resolve_conflicts", "review_model_alignment", "human_review"]
    ] = Field(max_length=4)
    abstain: bool = Field(strict=True)
    uncertainty: Literal["requires_human_semantic_review"]

    def local_proposal(self):
        groups = {"calculated_fact": [], "observed_fact": [], "model_signal": []}
        for finding in self.findings:
            row = finding.model_dump()
            numbers = []
            for number in finding.numeric_statements:
                # Empty strings denote only nullable metadata, never an amount.
                # Partial or invalid windows remain rejected locally.
                numbers.append(
                    dict(
                        metric=number.metric,
                        value=number.value,
                        currency=number.currency or None,
                        feature=number.feature or None,
                        window=None
                        if number.window_start == number.window_end == ""
                        else dict(start=number.window_start, end=number.window_end),
                    )
                )
            row["numeric_statements"] = numbers
            groups[finding.claim_type].append(row)
        return AIProposal.model_validate(
            dict(
                **self.model_dump(exclude={"findings", "hypotheses"}),
                financial_observations=groups["calculated_fact"],
                unusual_activity=groups["observed_fact"],
                model_signals=groups["model_signal"],
                risk_indicators=[h.model_dump() for h in self.hypotheses],
            )
        )


class GroundedWireProposal(WireProposal):
    regulatory_binding_sha256: str
    regulatory_citations: list[str] = Field(max_length=5)

    def local_proposal(self):
        from app.schemas.regulatory_investigation import GroundedAIProposal

        # Reuse the original strict financial projection, then validate citation
        # identities with the existing grounded contract and independent verifier.
        financial = WireProposal.model_validate(
            self.model_dump(exclude={"regulatory_binding_sha256", "regulatory_citations"})
        ).local_proposal()
        return GroundedAIProposal.model_validate(
            {
                **financial.model_dump(),
                "regulatory_binding_sha256": self.regulatory_binding_sha256,
                "regulatory_citations": self.regulatory_citations,
            }
        )


class WireFindingCitation(Contract):
    finding_reference_id: str
    regulatory_citation: str


class ResearchWireProposal(GroundedWireProposal):
    """flat_selection_v3 (research only): links each finding to the retrieved sources used."""

    finding_citations: list[WireFindingCitation] = Field(max_length=40)

    def local_proposal(self):
        from app.schemas.research_demo import ResearchAIProposal

        grounded = GroundedWireProposal.model_validate(
            self.model_dump(exclude={"finding_citations"})
        ).local_proposal()
        return ResearchAIProposal.model_validate(
            {
                **grounded.model_dump(),
                "finding_citations": [c.model_dump() for c in self.finding_citations],
            }
        )


def wire_class(*, grounded=False, wire_format=WIRE_FORMAT):
    if wire_format == "flat_selection_v3":
        if not grounded:
            raise ValueError("flat_selection_v3 requires grounded research input")
        return ResearchWireProposal
    return GroundedWireProposal if grounded else WireProposal


def wire_schema(*, grounded=False, wire_format=WIRE_FORMAT):
    source = wire_class(grounded=grounded, wire_format=wire_format).model_json_schema()
    definitions = source.get("$defs", {})
    keep = {"type", "properties", "required", "additionalProperties", "items", "enum", "const"}

    def inline(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return inline(deepcopy(definitions[value["$ref"].split("/")[-1]]))
            result = {key: inline(item) for key, item in value.items() if key in keep}
            if "properties" in value:
                result["properties"] = {
                    key: inline(item) for key, item in value["properties"].items()
                }
            return result
        if isinstance(value, list):
            return [inline(item) for item in value]
        return value

    return inline(source)


WIRE_INSTRUCTIONS = (
    " Use flat_selection_v2: put each selected observation in findings, preserving its "
    "claim_type and exact references; put hypotheses in hypotheses. Finding reference_id by "
    "claim_type: observed_fact uses a supplied transaction reference_id, calculated_fact uses "
    "a supplied financial_fact reference_id, model_signal uses the supplied model_signal "
    "assessment_id. Each claim_type and reference_id pair appears at most once; at most 8 "
    "observed_fact, 8 calculated_fact and 1 model_signal findings. supporting_records and "
    "every supporting_evidence and contradictory_evidence list contain only supplied "
    "evidence_references values, each at most once, never a financial_fact or model_signal "
    "identifier. observed_fact supporting_evidence is exactly its own transaction reference_id. "
    "Each finding may "
    "contain no more than 5 numeric_statements. Numeric metrics by claim_type: "
    "observed_fact uses only amount, with that transaction's currency and an empty window; "
    "calculated_fact uses only observed_total and "
    "observed_count, with that fact's currency and window (also for observed_count) and "
    "supporting_evidence equal to "
    "its input_record_ids; model_signal uses only score, shap_base and shap_contribution "
    "(shap_contribution requires the feature name), has empty supporting_evidence, and empty "
    "currency and window. feature is empty except for shap_contribution. "
    "Numeric values must be exact decimal strings from the evidence. "
    "For numeric metadata only, use an empty string when currency, window_start, window_end "
    "or feature is absent. Never use an empty string for an amount. Copy "
    "missing_or_contradictory_evidence and uncertainty_limitations exactly from the supplied "
    "missing_evidence/conflicts and limitations. follow_up_questions and "
    "additional_information_needed contain only supplied question codes (never missing "
    "evidence codes), each at most once; use an empty list when none apply. Hypothesis "
    "question_code is not taken from the supplied questions: "
    "use only review_observed_concentration (requires supporting transaction references), "
    "coverage_gap_requires_more_evidence (only when missing evidence is supplied) or "
    "resolve_conflicting_observations (only when conflicts are supplied), each question_code "
    "at most once. next_steps contains "
    "only the codes collect_missing_evidence, resolve_conflicts (only when conflicts are "
    "supplied), review_model_alignment and human_review, each at most once, never free text. "
    "If evidence_requires_abstention is true, set abstain to true and overview to "
    "insufficient_evidence. overview review_supplied_evidence requires non-empty "
    "supporting_records. Abstain when required."
)

FINDING_CITATION_INSTRUCTIONS = (
    " flat_selection_v3: finding_citations links a finding to a supplied regulatory passage it "
    "relates to. Each entry uses a finding reference_id you returned in findings and a "
    "passage reference_id you also listed in regulatory_citations; each pair at most once. "
    "Every passage in regulatory_citations must appear in at least one finding_citations "
    "entry. A link is research context only, never a claim of legal applicability."
)
