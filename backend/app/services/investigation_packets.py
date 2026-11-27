"""Bounded producer using authorized projections; no provider, regulatory or ML invocation."""

from app.schemas.evidence_read import (
    AnalyticsRequest,
    CustomerRequest,
    ReadRequest,
    TransactionRequest,
)
from app.schemas.investigations import FinancialFact, InvestigationPacketBody, PacketContext
from app.services.evidence_read import ReadLimit, SnapshotStale


def packet_policy(
    *,
    missing_categories,
    partial,
    conflict,
    unknown_time,
    omitted_currency,
    model_missing,
    input_mismatch,
    transaction_count,
):
    missing = sorted(
        set(missing_categories)
        | {
            "settlement_status",
            "sampling_metadata",
            "comparable_expected_activity",
            "curated_documents",
        }
        | ({"selected_model_assessment"} if model_missing else set())
    )
    conflicts = ["contradictory_kyc_observations"] if conflict else []
    limits = [
        "deterministic_foundation_not_validated_ai_investigator",
        "synthetic_observations_only",
        "gross_observations_not_settled_cashflow",
        "observations_include_all_authorized_times_calculations_use_requested_window",
        "no_external_or_regulatory_context",
        "human_semantic_review_required",
    ]
    questions = [
        "obtain_comparable_declared_activity_expectations",
        "review_authorized_source_observations",
    ]
    abstentions = ["no_money_laundering_violation_or_sar_conclusion"]
    for flag, code, question in [
        (partial, "incomplete_evidence_not_zero_activity", "obtain_complete_requested_window"),
        (conflict, "contradictory_kyc_observations", "resolve_conflicting_kyc"),
        (unknown_time > 0, "unknown_event_times_not_inferred", "obtain_recorded_event_timezones"),
        (omitted_currency, "unrequested_currencies_not_aggregated", "review_currency_selection"),
        (
            input_mismatch,
            "evidence_differs_from_immutable_alert_inputs",
            "review_model_input_alignment",
        ),
    ]:
        if flag:
            limits.append(code)
            questions.append(question)
    insufficient = (
        partial or conflict or unknown_time > 0 or omitted_currency or not transaction_count
    )
    if insufficient:
        abstentions.append("insufficient_evidence_for_behavioral_interpretation")
    return dict(
        outcome="abstained" if insufficient else "packet_ready",
        missing_evidence=missing,
        conflicts=conflicts,
        limitations=limits,
        questions=questions,
        abstentions=abstentions,
    )


def assemble(reader, run, manifest, step):
    actor, case = run.actor_id, run.case_id
    context = step(lambda: reader.get_case_context(actor, case, manifest.request.assessment_id))
    if context.snapshot != manifest.snapshot:
        raise SnapshotStale("investigation_input_invalidated")
    token = context.data.snapshot_token
    transactions = []
    cursor = None
    for _ in range(4):
        page = step(
            lambda: reader.get_transactions(
                actor, case, TransactionRequest(snapshot=token, limit=50, cursor=cursor)
            )
        )
        transactions.extend(page.data.items)
        cursor = page.data.next_cursor
        if cursor is None:
            break
    if cursor is not None or len(transactions) > 200:
        raise ReadLimit("investigation_record_limit")
    conflict = False
    cursor = None
    for _ in range(10):
        page = step(
            lambda: reader.get_customer_context(
                actor, case, CustomerRequest(snapshot=token, limit=20, cursor=cursor)
            )
        )
        conflict = conflict or any(r.contradictory_observations for r in page.data.items)
        cursor = page.data.next_cursor
        if cursor is None:
            break
    if cursor is not None:
        raise ReadLimit("investigation_customer_limit")
    model = step(lambda: reader.get_model_assessment(actor, case, ReadRequest(snapshot=token)))
    facts = []
    for currency in manifest.request.currencies:
        for calculation in ("count_totals", "concentration"):
            query = AnalyticsRequest(
                snapshot=token,
                calculation=calculation,
                window=manifest.request.window,
                currency=currency,
            )
            result = step(lambda: reader.calculate_activity(actor, case, query))
            inputs = [
                t.reference.record_version_id
                for t in transactions
                if t.currency == currency
                and t.event_at is not None
                and query.window.start <= t.event_at < query.window.end
            ]
            facts.append(
                FinancialFact(
                    reference_id=result.reference_id,
                    input_record_ids=inputs,
                    coverage=result.coverage,
                    result=result.data,
                )
            )
    policy = packet_policy(
        missing_categories=context.data.missing_categories,
        partial=any(f.coverage.status != "complete_declared_window" for f in facts),
        conflict=conflict,
        unknown_time=sum(t.event_at is None for t in transactions),
        omitted_currency=any(t.currency not in manifest.request.currencies for t in transactions),
        model_missing=model.data.assessment is None,
        input_mismatch=any(
            s.case_input_reconciliation != "matches_declared_inputs" for s in context.sources
        ),
        transaction_count=len(transactions),
    )
    return InvestigationPacketBody(
        run_id=run.id,
        manifest_sha256=run.manifest_sha256,
        context=PacketContext(
            case_id=case,
            state=context.data.state,
            human_disposition=context.data.disposition,
            available_categories=context.data.available_categories,
            missing_categories=context.data.missing_categories,
        ),
        transactions=transactions,
        facts=facts,
        model_signal=model.data.assessment,
        evidence=context.evidence,
        **policy,
    )
