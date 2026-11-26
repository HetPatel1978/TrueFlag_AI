"""Constrained proposals -> server facts. No provider-supplied factual narrative is trusted."""

from decimal import Decimal

from app.schemas.investigation_drafts import ProviderInput, ProviderProposal
from app.schemas.provider_live import AIProposal, LiveProviderConfig
from app.services.ingestion import digest
from app.services.investigation_provider import strict_json
from app.services.investigation_verifier import VerificationFailed


class DraftVerificationFailure(VerificationFailed):
    """Fixed reason code only; never includes provider text or financial values."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__("draft_verification_failed")


def minimize(packet):
    """No actor/case/customer/account IDs, raw predictor values, source text or artifact hashes."""
    model = packet.model_signal
    return ProviderInput(
        packet_sha256=digest(packet.model_dump(mode="json")),
        evidence_requires_abstention=packet.outcome == "abstained",
        transactions=[
            dict(
                reference_id=str(t.reference.record_version_id),
                amount=str(t.amount),
                currency=t.currency,
                event_at=t.event_at.isoformat() if t.event_at else None,
                direction=t.direction,
            )
            for t in packet.transactions
        ],
        financial_facts=[
            dict(
                reference_id=str(f.reference_id),
                input_record_ids=[str(r) for r in f.input_record_ids],
                result=f.result.model_dump(
                    mode="json", exclude={"concentration": {"__all__": {"counterparty_handle"}}}
                ),
                coverage=f.coverage.model_dump(mode="json"),
            )
            for f in packet.facts
        ],
        model_signal=None
        if model is None
        else dict(
            assessment_id=str(model.assessment_id),
            model_version=model.model_version,
            score=model.score,
            policy=model.selected_policy,
            recommendation=model.recommended_route,
            policy_version=model.policy_version,
            shap_base=model.explanation.base_value,
            shap=[
                dict(name=f.name, contribution=f.contribution) for f in model.explanation.features
            ],
        ),
        missing_evidence=packet.missing_evidence,
        conflicts=packet.conflicts,
        limitations=packet.limitations,
        questions=packet.questions,
        evidence_references=[e.record_version_id for e in packet.evidence],
    )


def parse_proposal(reply, config):
    if reply.provider != config.provider or reply.model != config.model:
        raise VerificationFailed("draft_verification_failed")
    cls = AIProposal if isinstance(config, LiveProviderConfig) else ProviderProposal
    if (
        getattr(config, "regulatory_binding_sha256", None) is not None
        or getattr(config, "regulatory_query", None) is not None
        or getattr(config, "research_binding_sha256", None) is not None
    ):
        from app.schemas.regulatory_investigation import (
            GroundedAIProposal,
            GroundedSimulationProposal,
        )

        cls = (
            GroundedAIProposal
            if isinstance(config, LiveProviderConfig)
            else GroundedSimulationProposal
        )
        if getattr(config, "wire_format", None) == "flat_selection_v3":
            from app.schemas.research_demo import ResearchAIProposal

            cls = ResearchAIProposal
    return cls.model_validate(
        strict_json(
            reply.content,
            16384 if isinstance(config, LiveProviderConfig) else config.max_output_tokens,
        )
    )


def validate_proposal(packet, proposal):
    """Parent verifier has independently recomputed raw facts before this selector validation."""
    permitted = {e.record_version_id for e in packet.evidence}
    if isinstance(proposal, AIProposal):
        if not set(proposal.supporting_records) <= permitted or len(
            proposal.supporting_records
        ) != len(set(proposal.supporting_records)):
            raise DraftVerificationFailure("supporting_reference_invalid")
        if set(proposal.missing_or_contradictory_evidence) != set(
            packet.missing_evidence + packet.conflicts
        ):
            raise DraftVerificationFailure("missing_evidence_mismatch")
        if set(proposal.uncertainty_limitations) != set(packet.limitations):
            raise DraftVerificationFailure("limitations_mismatch")
        if (
            any(f.claim_type != "calculated_fact" for f in proposal.financial_observations)
            or any(f.claim_type != "observed_fact" for f in proposal.unusual_activity)
            or any(f.claim_type != "model_signal" for f in proposal.model_signals)
        ):
            raise DraftVerificationFailure("claim_type_mismatch")
        if (packet.outcome == "abstained" and proposal.overview != "insufficient_evidence") or (
            proposal.overview == "review_supplied_evidence" and not proposal.supporting_records
        ):
            raise DraftVerificationFailure("overview_mismatch")
        proposal = proposal.selection()
    transactions = {t.reference.record_version_id: t for t in packet.transactions}
    calculations = {f.reference_id: f for f in packet.facts}
    questions = set(packet.questions)
    model = packet.model_signal
    if proposal.packet_sha256 != digest(packet.model_dump(mode="json")):
        raise DraftVerificationFailure("packet_hash_mismatch")
    for selected in [proposal.questions, proposal.unresolved_questions]:
        if len(selected) != len(set(selected)) or not set(selected) <= questions:
            raise DraftVerificationFailure("question_mismatch")
    seen = set()
    findings = []
    for finding in proposal.findings:
        key = (finding.claim_type, finding.reference_id)
        if key in seen:
            raise DraftVerificationFailure("duplicate_finding")
        seen.add(key)
        supporting = set(finding.supporting_evidence)
        contradictory = set(finding.contradictory_evidence)
        if not supporting <= permitted or not contradictory <= permitted:
            raise DraftVerificationFailure("reference_not_authorized")
        if finding.claim_type == "observed_fact":
            tx = transactions.get(finding.reference_id)
            if tx is None or supporting != {finding.reference_id}:
                raise DraftVerificationFailure("transaction_reference_mismatch")
            summary = tx.model_dump(mode="json")
            allowed = {"amount": tx.amount}
            currency, window = tx.currency, None
        elif finding.claim_type == "calculated_fact":
            fact = calculations.get(finding.reference_id)
            if fact is None or supporting != set(fact.input_record_ids):
                raise DraftVerificationFailure("calculation_reference_mismatch")
            summary = fact.model_dump(mode="json")
            allowed = {
                "observed_total": fact.result.observed_total,
                "observed_count": fact.result.observed_count,
            }
            currency, window = fact.result.currency, fact.result.window
        else:
            if model is None or finding.reference_id != model.assessment_id or supporting:
                raise DraftVerificationFailure("model_signal_mismatch")
            summary = model.model_dump(mode="json")
            allowed = {"score": model.score, "shap_base": model.explanation.base_value}
            currency = window = None
        for number in finding.numeric_statements:
            value = allowed.get(number.metric)
            if finding.claim_type == "model_signal" and number.metric == "shap_contribution":
                matches = [
                    f.contribution for f in model.explanation.features if f.name == number.feature
                ]
                value = matches[0] if len(matches) == 1 else None
            elif number.feature is not None:
                raise DraftVerificationFailure("numeric_feature_mismatch")
            if (
                value is None
                or number.value != Decimal(str(value))
                or number.currency != currency
                or number.window != window
            ):
                raise DraftVerificationFailure("numeric_value_mismatch")
        findings.append(
            dict(
                claim_type=finding.claim_type,
                reference_id=str(finding.reference_id),
                supporting_evidence=[str(r) for r in finding.supporting_evidence],
                contradictory_evidence=[str(r) for r in finding.contradictory_evidence],
                server_generated_summary=summary,
                interpretation="model_signal_not_probability_of_crime"
                if finding.claim_type == "model_signal"
                else "source_or_derived_observation_not_criminal_finding",
            )
        )
    hypothesis_codes = set()
    for hypothesis in proposal.hypotheses:
        if (
            hypothesis.question_code in hypothesis_codes
            or not set(hypothesis.supporting_evidence) <= permitted
            or not set(hypothesis.contradictory_evidence) <= permitted
        ):
            raise DraftVerificationFailure("hypothesis_reference_invalid")
        hypothesis_codes.add(hypothesis.question_code)
        if hypothesis.question_code == "resolve_conflicting_observations" and not packet.conflicts:
            raise DraftVerificationFailure("conflicts_hypothesis_unsupported")
        if (
            hypothesis.question_code == "coverage_gap_requires_more_evidence"
            and not packet.missing_evidence
        ):
            raise DraftVerificationFailure("coverage_hypothesis_unsupported")
        if hypothesis.question_code == "review_observed_concentration" and (
            not packet.transactions or not hypothesis.supporting_evidence
        ):
            raise DraftVerificationFailure("concentration_hypothesis_unsupported")
    if packet.outcome == "abstained" and not proposal.abstain:
        # Incomplete/conflicting evidence cannot be converted to confident provider output.
        raise DraftVerificationFailure("abstention_required")
    if "resolve_conflicts" in proposal.next_steps and not packet.conflicts:
        raise DraftVerificationFailure("conflict_step_unsupported")
    return findings
