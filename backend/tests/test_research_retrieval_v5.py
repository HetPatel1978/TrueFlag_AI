"""Retrieval v5: case-specific terms, deterministic evidence-pattern rules, coverage ranking."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.schemas.research_demo import (
    ResearchBindingV4,
    ResearchBindingV5,
    ResearchRetrievalV4,
    parse_binding,
)
from app.services import research_retrieval as rr
from app.services.research_demo import ResearchEvidenceService

START = datetime(2025, 10, 3, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, tzinfo=timezone.utc)


def txn(day, amount, direction="credit", channel="internal", counterparty="cp-1", hour=12):
    return {
        "amount": str(amount),
        "currency": "USD",
        "event_at": (START + timedelta(days=day, hours=hour)).isoformat(),
        "direction": direction,
        "channel": channel,
        "counterparty_handle": counterparty,
    }


def packet(transactions, drivers=("totalPaymentAmt90d",)):
    return {
        "model_signal": {
            "explanation": {
                "features": [
                    {
                        "name": n,
                        "contribution": 0.1 - i / 100,
                        "direction": "raises_score",
                        "missing": False,
                    }
                    for i, n in enumerate(drivers)
                ]
            }
        },
        "transactions": transactions,
        "facts": [
            {
                "result": {
                    "concentration": [1],
                    "window": {"start": START.isoformat(), "end": END.isoformat()},
                }
            }
        ],
        "missing_evidence": [
            "comparable_expected_activity",
            "curated_documents",
            "sampling_metadata",
            "settlement_status",
        ],
        "conflicts": [],
    }


def rules(transactions, income=50000):
    return [p["rule"] for p in rr.evidence_patterns(packet(transactions), income)]


# ---- each rule fires at its threshold and not below ---------------------------------------


def test_cash_below_reporting_threshold_needs_three_cash_deposits_of_9000_to_9999():
    near = [txn(d, 9500, channel="cashlike", counterparty=None) for d in (1, 9, 17)]
    assert "cash_below_reporting_threshold" in rules(near)
    assert "cash_below_reporting_threshold" not in rules(near[:2])
    at_limit = [txn(d, 10000, channel="cashlike", counterparty=None) for d in (1, 9, 17)]
    assert "cash_below_reporting_threshold" not in rules(at_limit)  # 10,000 is reportable
    not_cash = [txn(d, 9500) for d in (1, 9, 17)]
    assert "cash_below_reporting_threshold" not in rules(not_cash)


def test_rapid_in_out_needs_three_pairs_out_within_48_hours_at_90_to_100_percent():
    pairs = []
    for n in range(3):
        pairs += [txn(10 * n, 1000), txn(10 * n + 1, 950, direction="debit", counterparty="cp-2")]
    assert "rapid_in_out" in rules(pairs)
    assert "rapid_in_out" not in rules(pairs[:4])
    slow = []
    for n in range(3):
        slow += [txn(10 * n, 1000), txn(10 * n + 3, 950, direction="debit")]
    assert "rapid_in_out" not in rules(slow)  # 72 hours later
    small = []
    for n in range(3):
        small += [txn(10 * n, 1000), txn(10 * n + 1, 800, direction="debit")]
    assert "rapid_in_out" not in rules(small)  # only 80% leaves


def test_many_sources_needs_ten_distinct_senders():
    assert "many_sources" in rules([txn(d, 200, counterparty=f"s{d}") for d in range(10)])
    assert "many_sources" not in rules([txn(d, 200, counterparty=f"s{d}") for d in range(9)])


def test_activity_above_declared_income_annualizes_outgoing_against_three_times_income():
    # 89 days: USD 37,000 out -> about 151,700 a year; 3 x 50,000 = 150,000.
    out = [txn(1, 37000, direction="debit")]
    found = rr.evidence_patterns(packet(out), 50000)
    assert [p["rule"] for p in found] == ["activity_above_declared_income"]
    assert found[0]["threshold"] == "150000"
    assert "activity_above_declared_income" not in rules([txn(1, 30000, direction="debit")])
    assert "activity_above_declared_income" not in rules(out, income=None)  # never inferred


def test_dormant_then_active_needs_sixty_quiet_days_and_ten_transactions():
    late = [txn(75 + n % 10, 300, direction="debit") for n in range(10)]
    assert "dormant_then_active" in rules(late)
    assert "dormant_then_active" not in rules(late[:9])
    assert "dormant_then_active" not in rules([txn(30 + n, 300) for n in range(10)])


def test_transactions_without_time_or_in_another_currency_are_ignored():
    near = [txn(d, 9500, channel="cashlike", counterparty=None) for d in (1, 9, 17)]
    near[0]["event_at"] = None
    near[1]["currency"] = "CAD"
    assert rules(near) == []


# ---- inputs, terms and records ---------------------------------------------------------


def test_v5_drops_inputs_present_in_every_case_and_adds_fired_patterns():
    near = [txn(d, 9500, channel="cashlike", counterparty=None) for d in (1, 9, 17)]
    inputs, patterns, dropped = rr.case_inputs_v5(packet(near), 50000)
    assert inputs == [
        "risk_driver:totalPaymentAmt90d",
        "evidence_pattern:cash_below_reporting_threshold",
    ]
    assert set(dropped) == set(rr.ALWAYS_PRESENT_INPUTS)
    assert patterns == [
        {"rule": "cash_below_reporting_threshold", "observed": "3", "threshold": "3"}
    ]
    # v1-v4 inputs are unchanged by v5.
    assert "calculation:counterparty_concentration" in rr.case_inputs(packet(near))


def test_pattern_terms_weigh_three_times_case_terms_and_every_rule_has_four_terms():
    weighted = dict(
        rr.weighted_terms_v5(
            [
                "risk_driver:nbrPaymentsCashLike90d",
                "evidence_pattern:cash_below_reporting_threshold",
            ]
        )
    )
    assert weighted["structured"] == weighted["currency"] == 3  # pattern beats the driver term
    assert weighted["cash"] == 1
    assert all(len(terms.split()) == 4 for _, terms in rr.PATTERN_RULES.values())


def test_binding_v5_parses_as_v5_and_v4_still_parses_as_v4():
    assert ResearchBindingV5.model_fields["retrieval"].annotation is ResearchRetrievalV4
    assert parse_binding.__module__ == "app.schemas.research_demo"
    assert issubclass(ResearchBindingV5, ResearchBindingV4)


# ---- real PostgreSQL ranking over the real snapshot -----------------------------------


@pytest.fixture(scope="module")
def session():
    url = os.environ.get("TRUEFLAG_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL test database required")
    engine = create_engine(url)
    with Session(engine) as value:
        yield value
    engine.dispose()


@pytest.fixture(scope="module")
def corpus():
    service = object.__new__(ResearchEvidenceService)
    _, chunks = service._corpus()
    return chunks


def test_v5_orders_scores_numerically(session, corpus):
    weighted = rr.weighted_terms_v5(
        ["risk_driver:totalPaymentAmt90d", "evidence_pattern:rapid_in_out"]
    )
    ranked, matched = rr.rank_v5(session, corpus, weighted)
    scores = [float(s) for _, s in ranked]
    assert scores == sorted(scores, reverse=True) and matched >= len(ranked)


def test_structuring_case_ranks_a_currency_transaction_reporting_section_first(session, corpus):
    from app.services import demo_case_catalog as catalog

    bundle = catalog.bundle("SYN-01-STRUCTURING")
    transactions = [
        txn(0, 0)
        | {
            "amount": str(t.amount),
            "event_at": t.event_at.isoformat(),
            "direction": t.direction,
            "channel": t.channel,
            "counterparty_handle": t.counterparty_key,
        }
        for t in bundle.records
        if t.kind == "transaction"
    ]
    drivers = ("totalMerchCred90d", "totalPaymentAmt90d", "nbrPaymentsCashLike90d")
    inputs, patterns, _ = rr.case_inputs_v5(packet(transactions, drivers), 48000)
    assert "evidence_pattern:cash_below_reporting_threshold" in inputs
    ranked, _ = rr.rank_v5(session, corpus, rr.weighted_terms_v5(inputs))
    assert ranked[0][0] in {"1020.310", "1020.311", "1020.312", "1020.313", "1020.314", "1020.315"}


def test_v5_retrieval_record_is_deterministic_and_stores_its_rule(monkeypatch, session, corpus):
    from uuid import uuid4

    service = object.__new__(ResearchEvidenceService)
    monkeypatch.setattr(service, "_scope", lambda *a: None, raising=False)
    near = [txn(d, 9500, channel="cashlike", counterparty=None) for d in (1, 9, 17)]
    inputs, patterns, dropped = rr.case_inputs_v5(packet(near), 50000)
    case, run = uuid4(), uuid4()
    v5 = dict(patterns=patterns, dropped=dropped)
    first = service._retrieve(session, None, case, run, inputs, v5=v5)
    retrieval = first[2]
    assert isinstance(retrieval, ResearchRetrievalV4)
    assert [p.rule for p in retrieval.patterns] == ["cash_below_reporting_threshold"]
    assert set(retrieval.dropped_inputs) == set(dropped)
    assert {w.term: w.weight for w in retrieval.weighted_terms}["structured"] == 3
    assert service._retrieve(session, None, case, run, inputs, v5=v5) == first
