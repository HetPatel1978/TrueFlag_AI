"""Constrained proposals -> server facts. No provider-supplied factual narrative is trusted."""

from decimal import Decimal

from app.schemas.investigation_drafts import ProviderInput, ProviderProposal
from app.services.ingestion import digest
from app.services.investigation_provider import strict_json
from app.services.investigation_verifier import VerificationFailed


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
    return ProviderProposal.model_validate(strict_json(reply.content, config.max_output_tokens))


def validate_proposal(packet, proposal):
    """Parent verifier has independently recomputed raw facts before this selector validation."""
    permitted = {e.record_version_id for e in packet.evidence}
    transactions = {t.reference.record_version_id: t for t in packet.transactions}
    calculations = {f.reference_id: f for f in packet.facts}
    questions = set(packet.questions)
    model = packet.model_signal
    if proposal.packet_sha256 != digest(packet.model_dump(mode="json")):
        raise VerificationFailed("draft_verification_failed")
    for selected in [proposal.questions, proposal.unresolved_questions]:
        if len(selected) != len(set(selected)) or not set(selected) <= questions:
            raise VerificationFailed("draft_verification_failed")
    seen = set()
    findings = []
    for finding in proposal.findings:
        key = (finding.claim_type, finding.reference_id)
        if key in seen:
            raise VerificationFailed("draft_verification_failed")
        seen.add(key)
        supporting = set(finding.supporting_evidence)
        contradictory = set(finding.contradictory_evidence)
        if not supporting <= permitted or not contradictory <= permitted:
            raise VerificationFailed("draft_verification_failed")
        if finding.claim_type == "observed_fact":
            tx = transactions.get(finding.reference_id)
            if tx is None or supporting != {finding.reference_id}:
                raise VerificationFailed("draft_verification_failed")
            summary = tx.model_dump(mode="json")
            allowed = {"amount": tx.amount}
            currency, window = tx.currency, None
        elif finding.claim_type == "calculated_fact":
            fact = calculations.get(finding.reference_id)
            if fact is None or supporting != set(fact.input_record_ids):
                raise VerificationFailed("draft_verification_failed")
            summary = fact.model_dump(mode="json")
            allowed = {
                "observed_total": fact.result.observed_total,
                "observed_count": fact.result.observed_count,
            }
            currency, window = fact.result.currency, fact.result.window
        else:
            if model is None or finding.reference_id != model.assessment_id or supporting:
                raise VerificationFailed("draft_verification_failed")
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
                raise VerificationFailed("draft_verification_failed")
            if (
                value is None
                or number.value != Decimal(str(value))
                or number.currency != currency
                or number.window != window
            ):
                raise VerificationFailed("draft_verification_failed")
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
            raise VerificationFailed("draft_verification_failed")
        hypothesis_codes.add(hypothesis.question_code)
        if hypothesis.question_code == "resolve_conflicting_observations" and not packet.conflicts:
            raise VerificationFailed("draft_verification_failed")
        if (
            hypothesis.question_code == "coverage_gap_requires_more_evidence"
            and not packet.missing_evidence
        ):
            raise VerificationFailed("draft_verification_failed")
        if hypothesis.question_code == "review_observed_concentration" and (
            not packet.transactions or not hypothesis.supporting_evidence
        ):
            raise VerificationFailed("draft_verification_failed")
    if packet.outcome == "abstained" and not proposal.abstain:
        # Incomplete/conflicting evidence cannot be converted to confident provider output.
        raise VerificationFailed("draft_verification_failed")
    if "resolve_conflicts" in proposal.next_steps and not packet.conflicts:
        raise VerificationFailed("draft_verification_failed")
    return findings
