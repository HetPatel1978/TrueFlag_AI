"""Offline stage evaluators; raw-source oracles and runtime verifier remain independent gates."""

import time
from decimal import Decimal

from app.schemas.provider_live import AIProposal
from app.services.connected_scenarios import expected_activity
from app.services.investigation_draft_verifier import validate_proposal
from app.services.investigation_provider import strict_json
from app.services.investigation_verifier import VerificationFailed

from .oracles import requires_abstention, source_index, verify_fixture


def numeric_claims(bundle, source_id, packet, proposal):
    """Check each typed statement directly against raw source rows / independently checked facts."""
    source = source_index(bundle, source_id)
    facts = {f.reference_id: f for f in packet.facts}
    correct = total = 0
    for finding in (
        proposal.financial_observations + proposal.unusual_activity + proposal.model_signals
    ):
        for number in finding.numeric_statements:
            total += 1
            if finding.claim_type == "observed_fact":
                row = source.get(finding.reference_id, {}).get("payload", {})
                ok = (
                    number.metric == "amount"
                    and row.get("kind") == "transaction"
                    and number.value == Decimal(row["amount"])
                    and number.currency == row["currency"]
                    and number.window is None
                    and number.feature is None
                )
            elif finding.claim_type == "calculated_fact":
                fact = facts.get(finding.reference_id)
                truth = expected_activity(bundle, currency=fact.result.currency) if fact else None
                expected = (
                    truth["count"]
                    if truth and number.metric == "observed_count"
                    else Decimal(truth["total"])
                    if truth
                    and number.metric == "observed_total"
                    and (truth["count"] or bundle.coverage == "complete_declared_window")
                    else None
                )
                ok = (
                    expected is not None
                    and number.value == Decimal(str(expected))
                    and number.currency == fact.result.currency
                    and number.window == fact.result.window
                    and number.feature is None
                )
            else:
                # No fabricated synthetic model oracle; existing stored model checks do this separately.
                ok = False
            correct += bool(ok)
    return correct, total


def evaluate_response(bundle, source_id, packet, raw):
    started = time.perf_counter()
    result = dict(
        schema_valid=False,
        reference_valid=None,
        source_versions_valid=True,
        numeric_correct=0,
        numeric_total=0,
        abstention_correct=None,
        accepted=False,
        failure_class="schema_rejected",
        semantic_support=None,
        unsupported_factual_claim_rate=None,
        real_model_quality=None,
    )
    try:
        verify_fixture(bundle, source_id, packet)
    except ValueError:
        result.update(
            source_versions_valid=False,
            failure_class="source_integrity_rejected",
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
        return result
    try:
        proposal = AIProposal.model_validate(strict_json(raw, 16384))
    except (ValueError, TypeError, RecursionError):
        result["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return result
    result["schema_valid"] = True
    permitted = set(source_index(bundle, source_id))
    references = list(proposal.supporting_records)
    for finding in (
        proposal.financial_observations + proposal.unusual_activity + proposal.model_signals
    ):
        references += finding.supporting_evidence + finding.contradictory_evidence
        references.append(finding.reference_id)
    for indicator in proposal.risk_indicators:
        references += indicator.supporting_evidence + indicator.contradictory_evidence
    known = (
        permitted
        | {f.reference_id for f in packet.facts}
        | ({packet.model_signal.assessment_id} if packet.model_signal else set())
    )
    result["reference_count"] = len(references)
    result["valid_reference_count"] = sum(r in known for r in references)
    result["reference_valid"] = all(r in known for r in references)
    result["numeric_correct"], result["numeric_total"] = numeric_claims(
        bundle, source_id, packet, proposal
    )
    result["abstention_correct"] = not requires_abstention(bundle) or proposal.abstain
    try:
        validate_proposal(packet, proposal)
        if not result["reference_valid"] or result["numeric_correct"] != result["numeric_total"]:
            raise VerificationFailed("evaluation_independent_gate_failed")
        result.update(accepted=True, failure_class=None)
    except VerificationFailed:
        result["failure_class"] = (
            "reference_rejected"
            if not result["reference_valid"]
            else "numeric_rejected"
            if result["numeric_correct"] != result["numeric_total"]
            else "evidence_policy_rejected"
        )
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
    return result
