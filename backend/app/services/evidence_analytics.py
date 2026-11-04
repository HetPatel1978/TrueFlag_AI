"""Allowlisted Decimal arithmetic over an already authorized immutable input set."""

from collections import Counter, defaultdict
from datetime import timedelta, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from app.schemas.evidence_read import (
    AnalyticsResult,
    Concentration,
    RepeatedAmount,
    VelocityBucket,
    Window,
)


def in_window(row, window):
    return row.event_at is not None and window.start <= row.event_at < window.end


def calculate(transactions, query, coverage):
    # Never combine currencies, infer FX, or substitute unknown event times.
    base = [
        r
        for r in transactions
        if r.currency == query.currency
        and (query.account_handle is None or r.account_handle == query.account_handle)
        and in_window(r, query.window)
    ]
    by_identity = {r.reference.identity_id: r for r in base}
    reversals = [r for r in base if r.event_kind == "reversal"]
    targets = Counter(r.reverses_handle for r in reversals)
    excluded, unmatched, pairs = set(), 0, 0
    for reversal in reversals:
        target = by_identity.get(reversal.reverses_handle)
        valid = (
            target is not None
            and target.event_kind != "reversal"
            and targets[reversal.reverses_handle] == 1
            and target.amount == reversal.amount
            and target.currency == reversal.currency
            and target.account_handle is not None
            and target.account_handle == reversal.account_handle
            and target.direction != reversal.direction
        )
        if valid:
            pairs += 1
            excluded.update(
                (target.reference.record_version_id, reversal.reference.record_version_id)
            )
        else:
            unmatched += 1
    rows = [
        r
        for r in base
        if (query.direction is None or r.direction == query.direction)
        and (
            query.treatment == "gross_observations" or r.reference.record_version_id not in excluded
        )
    ]
    complete = coverage.status == "complete_declared_window"
    insufficient = (
        (not rows and not complete)
        or (query.treatment == "exclude_verified_reversals" and unmatched > 0)
        or query.calculation == "kyc_comparison"
    )
    status = (
        "insufficient_evidence"
        if insufficient
        else "complete_declared_window"
        if complete
        else "observed_only"
    )
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)) as context:
        # Inputs max 24 digits and 200 records. 50 digits prevents summation rounding.
        context.prec = 50
        total = sum((r.amount for r in rows), Decimal(0))
        incoming = [r for r in rows if r.direction == "credit"]
        outgoing = [r for r in rows if r.direction == "debit"]
        result = AnalyticsResult(
            calculation=query.calculation,
            status=status,
            currency=query.currency,
            window=query.window,
            treatment=query.treatment,
            observed_count=len(rows),
            observed_total=None if insufficient else total,
            incoming_count=len(incoming),
            outgoing_count=len(outgoing),
            incoming_total=None
            if insufficient or (not complete and not incoming)
            else sum((r.amount for r in incoming), Decimal(0)),
            outgoing_total=None
            if insufficient or (not complete and not outgoing)
            else sum((r.amount for r in outgoing), Decimal(0)),
            reversal_observations=len(reversals),
            verified_reversal_pairs_excluded=pairs
            if query.treatment == "exclude_verified_reversals"
            else 0,
            unmatched_reversals=unmatched,
        )
        if query.treatment == "exclude_verified_reversals" and unmatched:
            return result
        if query.calculation == "velocity":
            buckets, start = [], query.window.start.astimezone(timezone.utc)
            while start < query.window.end:
                end = min(start + timedelta(seconds=query.bucket_seconds), query.window.end)
                members = [r for r in rows if start <= r.event_at < end]
                buckets.append(
                    VelocityBucket(
                        window=Window(start=start, end=end),
                        observed_count=len(members),
                        observed_total=None
                        if insufficient or (not complete and not members)
                        else sum((r.amount for r in members), Decimal(0)),
                    )
                )
                start = end
            result = result.model_copy(update={"buckets": buckets})
        if query.calculation == "concentration":
            groups = defaultdict(list)
            unknown = 0
            for row in rows:
                if row.counterparty_handle is None:
                    unknown += 1
                else:
                    groups[row.counterparty_handle].append(row)
            ordered = sorted(
                groups, key=lambda k: (-sum((r.amount for r in groups[k]), Decimal(0)), str(k))
            )
            concentration = [
                Concentration(
                    counterparty_handle=k,
                    observed_count=len(groups[k]),
                    observed_total=sum((r.amount for r in groups[k]), Decimal(0)),
                    share_of_observed_amount=None
                    if total == 0
                    else (sum((r.amount for r in groups[k]), Decimal(0)) / total).quantize(
                        Decimal("0.0000000000000001")
                    ),
                )
                for k in ordered[:10]
            ]
            result = result.model_copy(
                update={
                    "concentration": concentration,
                    "unknown_counterparty_count": unknown,
                    "concentration_truncated": len(ordered) > 10,
                }
            )
        if query.calculation == "patterns":
            groups = Counter((r.amount, r.direction, r.counterparty_handle) for r in rows)
            repeated = sorted(
                (k for k, n in groups.items() if n >= query.repeated_minimum),
                key=lambda k: (-groups[k], k[0], k[1], str(k[2])),
            )
            result = result.model_copy(
                update={
                    "large_amount_criterion": query.large_amount,
                    "large_observed_count": sum(r.amount >= query.large_amount for r in rows),
                    "repeated_minimum": query.repeated_minimum,
                    "repeated_amounts": [
                        RepeatedAmount(
                            amount=k[0], direction=k[1], counterparty_handle=k[2], count=groups[k]
                        )
                        for k in repeated[:10]
                    ],
                    "repeated_groups_truncated": len(repeated) > 10,
                }
            )
        if query.calculation == "kyc_comparison":
            result = result.model_copy(
                update={
                    "expected_activity_comparison": "insufficient_comparable_declared_expectations"
                }
            )
        return result
