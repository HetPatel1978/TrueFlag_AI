import json
from decimal import Decimal
from uuid import UUID

import pytest
from evidence_oracles import PROFILE_EXPECTATIONS
from pydantic import ValidationError

from app.schemas.alerts import AlertFeatures
from app.schemas.evidence import PROFILES, TransactionObservation, money
from app.services.ingestion import digest
from app.services.synthetic_evidence import (
    bundle_manifest,
    canonical_records,
    generate_scenario,
    reconciliation,
)

SCENARIO = UUID("0665ed81-3b5c-4778-821d-9f45b221abec")


@pytest.mark.parametrize("profile", PROFILES)
def test_deterministic_bounded_profiles_and_label_isolation(profile):
    first = generate_scenario(SCENARIO, 17, profile)
    second = generate_scenario(SCENARIO, 17, profile)
    assert first == second
    assert digest(bundle_manifest(first)) == digest(bundle_manifest(second))
    records = canonical_records(first)
    count, coverage = PROFILE_EXPECTATIONS[profile]
    assert sum(r["kind"] == "transaction" for r in records.values()) == count
    assert first.coverage == coverage
    serialized = json.dumps(bundle_manifest(first))
    assert all(word not in serialized for word in ("oracle", "suspicious", "SAR", "label"))
    assert set(first.declarations) <= set(AlertFeatures.model_fields)
    assert reconciliation(first)["transaction_derived_fields"] == []
    if profile != "incomplete_features":
        assert len(first.declarations) == 27
        assert AlertFeatures.model_validate(first.declarations).model_dump() == first.declarations


@pytest.mark.parametrize("field", AlertFeatures.model_fields)
def test_every_missing_feature_blocks_reconciliation_without_zero_fill(field):
    bundle = generate_scenario(SCENARIO, 17)
    del bundle.declarations[field]
    outcome = reconciliation(bundle)
    assert outcome["status"] == "blocked"
    assert outcome["missing_fields"] == [field]
    assert outcome["fields"][field] == "missing"


@pytest.mark.parametrize(
    "value", [True, 1.2, "NaN", "Infinity", "1e3", "-1", "0.123456789", "10000000000000000"]
)
def test_money_rejects_inexact_nonfinite_or_unbounded_input(value):
    with pytest.raises(ValueError):
        money(value)


def test_null_zero_corrections_order_and_exact_money():
    assert generate_scenario(SCENARIO, 17, "missing_income").declarations["income"] is None
    assert generate_scenario(SCENARIO, 17, "zero_income").declarations["income"] == 0
    normal = generate_scenario(SCENARIO, 17)
    ordered = generate_scenario(SCENARIO, 17, "out_of_order")
    assert canonical_records(normal) == canonical_records(ordered)
    assert canonical_records(normal) != canonical_records(generate_scenario(SCENARIO, 18))
    precision = generate_scenario(SCENARIO, 17, "decimal_precision")
    assert precision.records[4].amount == Decimal("0.12345678")
    corrected = generate_scenario(SCENARIO, 17, source_revision=2)
    assert corrected.records[4].amount == normal.records[4].amount + 1
    assert normal.records[4].amount != corrected.records[4].amount


def test_invalid_time_and_conflicting_duplicate_are_rejected():
    bundle = generate_scenario(SCENARIO, 17)
    transaction = bundle.records[4]
    payload = transaction.model_dump()
    payload["event_at"] = transaction.event_at.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        TransactionObservation.model_validate(payload)
    conflict = transaction.model_copy(update={"amount": Decimal("99")})
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        canonical_records(bundle.model_copy(update={"records": (*bundle.records, conflict)}))
