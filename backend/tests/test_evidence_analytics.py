"""Independent small numeric oracles, not fabricated RF results."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.evidence_read import (
    AnalyticsRequest,
    Coverage,
    EvidenceReference,
    TransactionItem,
    Window,
)
from app.services.evidence_analytics import calculate

START = datetime(2025, 12, 1, tzinfo=timezone.utc)
WINDOW = Window(start=START, end=START + timedelta(days=2))
ACCOUNT, PARTY = uuid4(), uuid4()


def transaction(
    amount, *, currency="USD", direction="credit", hours=1, kind="payment", reverses=None
):
    return TransactionItem(
        reference=EvidenceReference(
            record_version_id=uuid4(),
            identity_id=uuid4(),
            source_version_id=uuid4(),
            kind="transaction",
            version=1,
            sha256="0" * 64,
        ),
        account_handle=ACCOUNT,
        counterparty_handle=PARTY,
        amount=Decimal(amount),
        currency=currency,
        event_at=START + timedelta(hours=hours),
        original_time=(START + timedelta(hours=hours)).isoformat(),
        event_kind=kind,
        direction=direction,
        channel="internal",
        reverses_handle=reverses,
    )


def request(calculation="count_totals", **kwargs):
    return AnalyticsRequest(
        snapshot="x" * 40, calculation=calculation, currency="USD", window=WINDOW, **kwargs
    )


def coverage(status="complete_declared_window"):
    return Coverage(status=status, requested=WINDOW, unknown_time_excluded=0, limitations=[])


def test_decimal_total_direction_currency_and_half_open_window():
    rows = [
        transaction("0.12345678"),
        transaction("0.20000002", direction="debit"),
        transaction("999", currency="CAD"),
        transaction("9", hours=48),
    ]
    with localcontext() as ctx:
        ctx.prec = 3  # Caller context must not round sums.
        result = calculate(rows, request(), coverage())
    assert result.observed_count == 2
    assert result.observed_total == Decimal("0.32345680")
    assert result.incoming_total == Decimal("0.12345678")
    assert result.outgoing_total == Decimal("0.20000002")


def test_json_windows_reject_inferred_epoch_units_and_missing_offsets():
    for bad in (0, "1234", "2025-12-01", "2025-12-01T00:00:00"):
        body = {
            "snapshot": "x" * 40,
            "calculation": "count_totals",
            "currency": "USD",
            "window": {"start": bad, "end": "2026-01-01T00:00:00Z"},
        }
        with pytest.raises(ValidationError):
            AnalyticsRequest.model_validate_json(json.dumps(body))


def test_gross_and_explicit_verified_reversal_treatments():
    original = transaction("12.25")
    reversal = transaction(
        "12.25", direction="debit", kind="reversal", reverses=original.reference.identity_id
    )
    rows = [original, reversal, transaction("3")]
    gross = calculate(rows, request(), coverage())
    adjusted = calculate(rows, request(treatment="exclude_verified_reversals"), coverage())
    assert (gross.observed_count, gross.observed_total) == (3, Decimal("27.50"))
    assert (adjusted.observed_count, adjusted.observed_total) == (1, Decimal("3"))
    assert adjusted.verified_reversal_pairs_excluded == 1
    assert gross.reversal_observations == 1


@pytest.mark.parametrize(
    "fault",
    ["missing_target", "wrong_amount", "same_direction", "duplicate_reversal", "outside_window"],
)
def test_unresolved_reversal_never_produces_adjusted_totals(fault):
    original = transaction("5", hours=-1 if fault == "outside_window" else 1)
    reversal = transaction(
        "6" if fault == "wrong_amount" else "5",
        direction="credit" if fault == "same_direction" else "debit",
        kind="reversal",
        reverses=uuid4() if fault == "missing_target" else original.reference.identity_id,
    )
    rows = [original, reversal]
    if fault == "duplicate_reversal":
        rows.append(
            reversal.model_copy(
                update={
                    "reference": reversal.reference.model_copy(
                        update={"record_version_id": uuid4()}
                    )
                }
            )
        )
    result = calculate(rows, request(treatment="exclude_verified_reversals"), coverage())
    assert result.status == "insufficient_evidence" and result.unmatched_reversals > 0
    assert result.observed_total is result.incoming_total is result.outgoing_total is None


@pytest.mark.parametrize("status", ["partial", "unavailable"])
def test_missing_coverage_is_not_zero_activity(status):
    result = calculate([], request(), coverage(status))
    assert result.status == "insufficient_evidence"
    assert result.observed_count == 0 and result.observed_total is None


def test_velocity_concentration_repetition_and_explicit_large_criterion():
    rows = [transaction("10", hours=1), transaction("10", hours=2), transaction("5", hours=25)]
    velocity = calculate(rows, request("velocity"), coverage())
    assert [r.observed_count for r in velocity.buckets] == [2, 1]
    assert [r.observed_total for r in velocity.buckets] == [Decimal(20), Decimal(5)]
    concentration = calculate(rows, request("concentration"), coverage())
    assert concentration.concentration[0].share_of_observed_amount == Decimal(1)
    patterns = calculate(rows, request("patterns", large_amount="10"), coverage())
    assert patterns.large_observed_count == 2
    assert patterns.repeated_amounts[0].count == 2
    assert patterns.repeated_amounts[0].amount == Decimal(10)
    kyc = calculate(rows, request("kyc_comparison"), coverage())
    assert kyc.expected_activity_comparison == "insufficient_comparable_declared_expectations"
    assert kyc.observed_total is None


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "BTC"},
        {"calculation": "arbitrary_sql"},
        {"repeated_minimum": True},
        {"large_amount": 0.1},
        {"large_amount": "NaN"},
        {"extra": "SELECT * FROM users"},
        {"window": {"start": "2025-12-01", "end": "2025-12-02"}},
        {"calculation": "patterns"},
        {
            "calculation": "velocity",
            "bucket_seconds": 3600,
            "window": Window(start=START, end=START + timedelta(days=10)),
        },
    ],
)
def test_strict_calculation_contract_rejects_unsupported_inputs(changes):
    body = dict(snapshot="x" * 40, calculation="count_totals", currency="USD", window=WINDOW)
    with pytest.raises(ValidationError):
        AnalyticsRequest(**{**body, **changes})
