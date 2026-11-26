"""Independent source-side checks. Never derive expected amounts from provider/packet totals."""

from datetime import datetime
from decimal import Decimal, localcontext
from uuid import uuid5

from app.services.connected_scenarios import expected_activity
from app.services.ingestion import digest
from app.services.synthetic_evidence import canonical_records


def source_index(bundle, source_id):
    return {
        uuid5(uuid5(source_id, key), "version:1"): dict(
            payload=payload,
            identity_id=uuid5(source_id, key),
            source_version_id=uuid5(source_id, "release:1"),
            sha256=digest(payload),
        )
        for key, payload in canonical_records(bundle).items()
    }


def requires_abstention(bundle):
    records = canonical_records(bundle).values()
    incomes = {r["annual_income"] for r in records if r["kind"] == "customer"}
    tx = [r for r in records if r["kind"] == "transaction"]
    return (
        bundle.coverage != "complete_declared_window"
        or len(incomes) > 1
        or not tx
        or any(t["event_at"] is None for t in tx)
    )


def verify_fixture(bundle, source_id, packet):
    """Fixture provenance gate, independent of runtime producer and proposal verifier."""
    if packet.model_signal is not None:
        raise ValueError("evaluation_unexpected_model_signal")
    index = source_index(bundle, source_id)
    if set(index) != {r.record_version_id for r in packet.evidence} or len(index) != len(
        packet.evidence
    ):
        raise ValueError("evaluation_source_membership_failed")
    for ref in list(packet.evidence) + [t.reference for t in packet.transactions]:
        if ref.record_version_id not in index:
            raise ValueError("evaluation_source_membership_failed")
        row = index[ref.record_version_id]
        if (
            ref.identity_id != row["identity_id"]
            or ref.source_version_id != row["source_version_id"]
            or ref.sha256 != row["sha256"]
            or ref.version != 1
            or ref.kind != row["payload"]["kind"]
        ):
            raise ValueError("evaluation_source_version_failed")
    transactions = {k: r for k, r in index.items() if r["payload"]["kind"] == "transaction"}
    if {t.reference.record_version_id for t in packet.transactions} != set(transactions) or len(
        packet.transactions
    ) != len(transactions):
        raise ValueError("evaluation_transaction_membership_failed")
    for tx in packet.transactions:
        row = transactions[tx.reference.record_version_id]["payload"]
        if (
            tx.amount != Decimal(row["amount"])
            or tx.currency != row["currency"]
            or tx.direction != row["direction"]
            or tx.event_kind != row["event_kind"]
            or tx.event_at != (datetime.fromisoformat(row["event_at"]) if row["event_at"] else None)
        ):
            raise ValueError("evaluation_transaction_values_failed")
    currencies = sorted({r["payload"]["currency"] for r in transactions.values()} or {"USD"})
    if len(packet.facts) != 2 * len(currencies) or {
        (f.result.currency, f.result.calculation) for f in packet.facts
    } != {(c, k) for c in currencies for k in ["count_totals", "concentration"]}:
        raise ValueError("evaluation_financial_plan_failed")
    for fact in packet.facts:
        result = fact.result
        if (
            result.window.start != bundle.window_start
            or result.window.end != bundle.as_of
            or result.treatment != "gross_observations"
        ):
            raise ValueError("evaluation_window_or_treatment_failed")
        expected = expected_activity(bundle, currency=result.currency)
        rows = {
            key: r["payload"]
            for key, r in transactions.items()
            if r["payload"]["currency"] == result.currency
            and r["payload"]["event_at"] is not None
            and bundle.window_start
            <= datetime.fromisoformat(r["payload"]["event_at"])
            < bundle.as_of
        }
        if set(fact.input_record_ids) != set(rows) or len(fact.input_record_ids) != len(rows):
            raise ValueError("evaluation_calculation_sources_failed")
        insufficient = not rows and bundle.coverage != "complete_declared_window"
        incoming = [r for r in rows.values() if r["direction"] == "credit"]
        outgoing = [r for r in rows.values() if r["direction"] == "debit"]
        with localcontext() as ctx:
            ctx.prec = 50
            expected_values = dict(
                observed_count=len(rows),
                observed_total=None if insufficient else Decimal(expected["total"]),
                incoming_count=len(incoming),
                outgoing_count=len(outgoing),
                incoming_total=None
                if insufficient or not incoming and bundle.coverage != "complete_declared_window"
                else sum((Decimal(r["amount"]) for r in incoming), Decimal(0)),
                outgoing_total=None
                if insufficient or not outgoing and bundle.coverage != "complete_declared_window"
                else sum((Decimal(r["amount"]) for r in outgoing), Decimal(0)),
                reversal_observations=sum(r["event_kind"] == "reversal" for r in rows.values()),
                verified_reversal_pairs_excluded=0,
            )
        if any(getattr(result, k) != v for k, v in expected_values.items()):
            raise ValueError("evaluation_financial_reconciliation_failed")
        if result.calculation == "concentration":
            groups = {
                uuid5(source_id, k): Decimal(v) for k, v in expected["counterparties"].items()
            }
            actual = {item.counterparty_handle: item for item in result.concentration}
            if set(actual) != set(groups):
                raise ValueError("evaluation_counterparty_membership_failed")
            with localcontext() as ctx:
                ctx.prec = 50
                for key, amount in groups.items():
                    count = sum(
                        uuid5(source_id, r["counterparty_key"]) == key for r in rows.values()
                    )
                    share = (
                        (amount / Decimal(expected["total"])).quantize(
                            Decimal("0.0000000000000001")
                        )
                        if Decimal(expected["total"])
                        else None
                    )
                    if (
                        actual[key].observed_total != amount
                        or actual[key].observed_count != count
                        or actual[key].share_of_observed_amount != share
                    ):
                        raise ValueError("evaluation_counterparty_values_failed")
    if (packet.outcome == "abstained") != requires_abstention(bundle):
        raise ValueError("evaluation_abstention_policy_failed")
    return index
