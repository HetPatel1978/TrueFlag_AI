"""Independent raw-record numeric/membership validator. Never calls producer analytics."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.models.evidence import EvidenceTransaction
from app.schemas.evidence_read import (
    CALCULATION_VERSION,
    RETRIEVAL_VERSION,
    AnalyticsRequest,
    AnalyticsResult,
    Concentration,
)
from app.schemas.investigations import VERIFIER_VERSION, InvestigationPacketBody
from app.services.evidence import EvidenceError
from app.services.evidence_read import KINDS, reference
from app.services.ingestion import digest
from app.services.investigation_packets import packet_policy


class VerificationFailed(EvidenceError):
    pass


def verify_packet(session, reader, context, manifest, body):
    packet = InvestigationPacketBody.model_validate_json(body.model_dump_json(warnings="error"))
    expected_refs = [reference(r) for r in context.rows]
    if packet.evidence != expected_refs or packet.manifest_sha256 != digest(
        manifest.model_dump(mode="json")
    ):
        raise VerificationFailed("investigation_verification_failed")
    raw = {
        r.record_version_id: r
        for r in session.scalars(
            select(EvidenceTransaction).where(
                EvidenceTransaction.record_version_id.in_(
                    [r.id for r in context.rows if r.kind == "transaction"]
                )
            )
        )
    }
    if len(raw) != len(packet.transactions) or len(
        {t.reference.record_version_id for t in packet.transactions}
    ) != len(raw):
        raise VerificationFailed("investigation_verification_failed")
    ordered = sorted(
        raw.values(),
        key=lambda r: (
            r.event_at is None,
            r.event_at or datetime.max.replace(tzinfo=timezone.utc),
            str(r.record_version_id),
        ),
    )
    if [t.reference.record_version_id for t in packet.transactions] != [
        r.record_version_id for r in ordered
    ]:
        raise VerificationFailed("investigation_verification_failed")
    accounts = {r.identity_id for r in context.rows if r.kind == "account"}
    identities = {r.id: r.identity_id for r in context.rows}
    refs = {r.record_version_id: r for r in expected_refs}
    txhandles = {r.identity_id for r in context.rows if r.kind == "transaction"}
    for item in packet.transactions:
        row = raw.get(item.reference.record_version_id)
        if row is None:
            raise VerificationFailed("investigation_verification_failed")
        fields = {
            "reference": refs[row.record_version_id],
            "account_handle": row.account_id if row.account_id in accounts else None,
            "counterparty_handle": row.counterparty_id if row.counterparty_id in accounts else None,
            "amount": row.amount,
            "currency": row.currency,
            "event_at": row.event_at,
            "original_time": row.original_time,
            "event_kind": row.event_kind,
            "direction": row.direction,
            "channel": row.channel,
            "settlement_status": "not_recorded",
            "reverses_handle": row.reverses_id if row.reverses_id in txhandles else None,
        }
        if any(getattr(item, key) != value for key, value in fields.items()):
            raise VerificationFailed("investigation_verification_failed")
    window = manifest.request.window
    plan = [(c, k) for c in manifest.request.currencies for k in ("count_totals", "concentration")]
    if [(f.result.currency, f.result.calculation) for f in packet.facts] != plan:
        raise VerificationFailed("investigation_verification_failed")
    for fact in packet.facts:
        currency = fact.result.currency
        rows = [
            r
            for r in raw.values()
            if r.currency == currency
            and r.event_at is not None
            and window.start <= r.event_at < window.end
        ]
        expected_ids = [r.record_version_id for r in ordered if r in rows]
        if fact.input_record_ids != expected_ids:
            raise VerificationFailed("investigation_verification_failed")
        unknown = sum(r.currency == currency and r.event_at is None for r in raw.values())
        complete = (
            bool(context.sources)
            and all(
                s.coverage == "complete_declared_window"
                and s.membership_complete
                and s.window.start <= window.start
                and s.window.end >= window.end
                for s in context.sources
            )
            and not unknown
        )
        coverage_status = (
            "unavailable"
            if not context.sources or all(s.coverage == "unavailable" for s in context.sources)
            else "complete_declared_window"
            if complete
            else "partial"
        )
        if (
            fact.coverage.status != coverage_status
            or fact.coverage.requested != window
            or fact.coverage.unknown_time_excluded != unknown
        ):
            raise VerificationFailed("investigation_verification_failed")
        expected_stats = dict(
            unknown_time_excluded=unknown,
            outside_window_excluded=sum(
                r.currency == currency
                and r.event_at is not None
                and not window.start <= r.event_at < window.end
                for r in raw.values()
            ),
            filter_excluded=sum(r.currency != currency for r in raw.values()),
        )
        expected_coverage = reader._coverage(context, window, expected_stats)
        reversals = [r for r in rows if r.event_kind == "reversal"]
        targets = Counter(r.reverses_id for r in reversals)
        by_identity = {identities[r.record_version_id]: r for r in rows}
        unmatched = 0
        for rev in reversals:
            target = by_identity.get(rev.reverses_id)
            if not (
                target is not None
                and target.event_kind != "reversal"
                and targets[rev.reverses_id] == 1
                and target.amount == rev.amount
                and target.currency == rev.currency
                and target.account_id in accounts
                and target.account_id == rev.account_id
                and target.direction != rev.direction
            ):
                unmatched += 1
        if unmatched:
            expected_coverage.limitations.append("unresolved_reversals_not_netted")
        if fact.coverage != expected_coverage:
            raise VerificationFailed("investigation_verification_failed")
        insufficient = not rows and not complete
        incoming = [r for r in rows if r.direction == "credit"]
        outgoing = [r for r in rows if r.direction == "debit"]
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
            total = sum((r.amount for r in rows), Decimal(0))
            expected = AnalyticsResult(
                calculation=fact.result.calculation,
                status="insufficient_evidence"
                if insufficient
                else "complete_declared_window"
                if complete
                else "observed_only",
                currency=currency,
                window=window,
                treatment="gross_observations",
                observed_count=len(rows),
                observed_total=None if insufficient else total,
                incoming_count=len(incoming),
                outgoing_count=len(outgoing),
                incoming_total=None
                if insufficient or not complete and not incoming
                else sum((r.amount for r in incoming), Decimal(0)),
                outgoing_total=None
                if insufficient or not complete and not outgoing
                else sum((r.amount for r in outgoing), Decimal(0)),
                reversal_observations=len(reversals),
                verified_reversal_pairs_excluded=0,
                unmatched_reversals=unmatched,
            )
            if fact.result.calculation == "concentration":
                groups = defaultdict(list)
                unknown_counterparty = 0
                for r in rows:
                    if r.counterparty_id not in accounts:
                        unknown_counterparty += 1
                    else:
                        groups[r.counterparty_id].append(r)
                sums = {
                    key: sum((r.amount for r in members), Decimal(0))
                    for key, members in groups.items()
                }
                concentration_order = sorted(groups, key=lambda key: (-sums[key], str(key)))
                expected = expected.model_copy(
                    update={
                        "concentration": [
                            Concentration(
                                counterparty_handle=key,
                                observed_count=len(groups[key]),
                                observed_total=sums[key],
                                share_of_observed_amount=None
                                if total == 0
                                else (sums[key] / total).quantize(Decimal("0.0000000000000001")),
                            )
                            for key in concentration_order[:10]
                        ],
                        "unknown_counterparty_count": unknown_counterparty,
                        "concentration_truncated": len(groups) > 10,
                    }
                )
        if fact.result != expected:
            raise VerificationFailed("investigation_verification_failed")
        # Validate the existing evidence-service reference, independently hashing the recomputed data.
        request = AnalyticsRequest(
            snapshot="x" * 32, calculation=expected.calculation, window=window, currency=currency
        )
        parameters = request.model_dump(mode="json", exclude={"snapshot", "cursor"})
        sha = digest(
            dict(
                operation="activity",
                parameters=parameters,
                snapshot=context.snapshot.model_dump(mode="json"),
                coverage=expected_coverage.model_dump(mode="json"),
                data=expected.model_dump(mode="json", exclude={"snapshot_token", "next_cursor"}),
            )
        )
        if fact.reference_id != uuid5(NAMESPACE_URL, RETRIEVAL_VERSION + ":" + sha):
            raise VerificationFailed("investigation_verification_failed")
    available = [kind for kind in KINDS if context.payloads[kind]]
    if packet.context.model_dump(mode="json") != {
        "case_id": str(context.case.id),
        "state": context.case.status,
        "human_disposition": context.case.disposition,
        "available_categories": available,
        "missing_categories": [k for k in KINDS if k not in available],
    }:
        raise VerificationFailed("investigation_verification_failed")
    model = reader._assessment(session, context)
    model_sha = digest(model.model_dump(mode="json")) if model else None
    if model_sha != manifest.assessment_sha256 or (
        packet.model_signal.model_dump(mode="json") if packet.model_signal else None
    ) != (model.model_dump(mode="json") if model else None):
        raise VerificationFailed("investigation_verification_failed")
    groups = defaultdict(set)
    for p in context.payloads["customer"].values():
        groups[(p.source_id, p.subject_key)].add((p.annual_income, p.currency, p.kyc_score))
    policy = packet_policy(
        missing_categories=[k for k in KINDS if k not in available],
        partial=any(f.coverage.status != "complete_declared_window" for f in packet.facts),
        conflict=any(len(values) > 1 for values in groups.values()),
        unknown_time=sum(r.event_at is None for r in raw.values()),
        omitted_currency=any(r.currency not in manifest.request.currencies for r in raw.values()),
        model_missing=model is None,
        input_mismatch=any(
            s.case_input_reconciliation != "matches_declared_inputs" for s in context.sources
        ),
        transaction_count=len(raw),
    )
    if any(getattr(packet, k) != v for k, v in policy.items()):
        raise VerificationFailed("investigation_verification_failed")
    return dict(
        verifier=VERIFIER_VERSION,
        status="source_numeric_reference_checks_passed",
        record_count=len(context.rows),
        transaction_count=len(raw),
        financial_facts=len(packet.facts),
        manifest_sha256=packet.manifest_sha256,
        packet_sha256=digest(packet.model_dump(mode="json")),
        calculation_version=CALCULATION_VERSION,
        human_semantic_review_required=True,
        legal_or_criminal_conclusion_validated=False,
    )
