"""Explicit denominators; offline containment never becomes live model quality."""

import math
import statistics
from decimal import Decimal


def ratio(n, d):
    return n / d if d else None


def aggregate(results):
    eligible = [r for r in results if r.get("status") == "evaluated"]
    parsed = [r for r in eligible if r["schema_valid"]]
    adversarial = [r for r in eligible if r.get("expected_acceptance") is False]
    abstentions = [r for r in parsed if r["abstention_required"]]
    injection = [
        r
        for r in adversarial
        if r["control"] in {"tool_escalation", "false_verification", "prompt_injection_instruction"}
    ]
    latency = sorted(r["elapsed_ms"] for r in eligible)
    return dict(
        evaluated_responses=len(eligible),
        blocked_or_unavailable_cases=len(
            {r["case_key"] for r in results if r.get("status") in {"not_materialized", "blocked"}}
        ),
        structured_output_acceptance_rate=ratio(
            sum(r["schema_valid"] for r in eligible), len(eligible)
        ),
        verified_output_acceptance_rate=ratio(sum(r["accepted"] for r in eligible), len(eligible)),
        evidence_reference_validity_rate=ratio(
            sum(r.get("valid_reference_count", 0) for r in parsed),
            sum(r.get("reference_count", 0) for r in parsed),
        ),
        numeric_claim_accuracy=ratio(
            sum(r["numeric_correct"] for r in parsed), sum(r["numeric_total"] for r in parsed)
        ),
        appropriate_required_abstention_rate=ratio(
            sum(r["abstention_correct"] for r in abstentions), len(abstentions)
        ),
        controlled_adversarial_rejection_rate=ratio(
            sum(not r["accepted"] for r in adversarial), len(adversarial)
        ),
        controlled_injection_containment_rate=ratio(
            sum(not r["accepted"] for r in injection), len(injection)
        ),
        deterministic_expectation_matches=sum(
            r["accepted"] == r["expected_acceptance"] for r in eligible
        ),
        deterministic_expectation_mismatches=sum(
            r["accepted"] != r["expected_acceptance"] for r in eligible
        ),
        denominators=dict(
            structured=len(eligible),
            references=sum(r.get("reference_count", 0) for r in parsed),
            numeric_claims=sum(r["numeric_total"] for r in parsed),
            required_abstentions=len(abstentions),
            adversarial=len(adversarial),
        ),
        evaluator_latency_ms_p50=statistics.median(latency) if latency else None,
        evaluator_latency_ms_p95=latency[max(0, math.ceil(len(latency) * 0.95) - 1)]
        if latency
        else None,
        semantic_support_score=None,
        unsupported_factual_claim_rate=None,
        reasoning_quality=None,
        real_model_injection_resistance=None,
        real_provider_latency_ms=None,
        real_provider_token_usage=None,
        real_provider_cost_per_investigation_usd=None,
        interpretation="Controlled fixtures include intentionally invalid outputs; these are verifier measurements, not model quality rates.",
    )


def operation_observation(
    *,
    mode,
    status,
    elapsed_ms,
    input_tokens=None,
    output_tokens=None,
    input_rate=None,
    output_rate=None,
):
    if (
        mode != "controlled_offline_fixture"
        or status
        not in {"completed", "timeout", "cancelled", "rate_limited", "failed", "incomplete"}
        or type(elapsed_ms) not in {int, float}
        or not math.isfinite(elapsed_ms)
        or elapsed_ms < 0
    ):
        raise ValueError("offline_operation_invalid")
    if any(v is not None and (type(v) is not int or v < 0) for v in [input_tokens, output_tokens]):
        raise ValueError("offline_usage_invalid")
    cost = None
    if all(v is not None for v in [input_tokens, output_tokens, input_rate, output_rate]):
        rates = [Decimal(str(input_rate)), Decimal(str(output_rate))]
        if any(not r.is_finite() or r < 0 for r in rates):
            raise ValueError("offline_rate_invalid")
        cost = str((input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000)
    return dict(
        mode=mode,
        status=status,
        controlled_elapsed_ms=elapsed_ms,
        reported_fixture_input_tokens=input_tokens,
        reported_fixture_output_tokens=output_tokens,
        configured_fixture_cost_estimate_usd=cost,
        vendor_usage_verified=False,
        real_inference_measured=False,
    )
