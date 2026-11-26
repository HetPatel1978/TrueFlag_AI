"""Pure deterministic catalog, provenance, accounting and frozen input semantics."""

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from app.schemas.alerts import AlertFeatures
from app.schemas.evidence import PROFILES
from app.services.connected_scenarios import (
    CATALOG,
    NAMESPACE,
    expected_activity,
    feature_origins,
    preview,
    scenario_bundle,
)
from app.services.evidence import EvidenceBlocked, checked_bundle
from app.services.ingestion import digest
from app.services.synthetic_evidence import bundle_manifest, canonical_records, generate_scenario

requires_dictionary = pytest.mark.skipif(
    not (
        Path(__file__).resolve().parents[2] / "assets/local/baseline/contracts/data_dictionary.csv"
    ).is_file(),
    reason="Approved private dictionary required; never substitute mock metadata for successful provenance",
)


@requires_dictionary
@pytest.mark.parametrize("spec", CATALOG, ids=lambda s: s.key)
def test_catalog_reproducible_complete_source_references_and_declared_features(spec):
    a = scenario_bundle(spec.key)
    assert a == scenario_bundle(spec.key) == checked_bundle(a)
    assert a.scenario_id == uuid5(NAMESPACE, "1701:" + spec.key)
    assert scenario_bundle(spec.key, 1702).scenario_id != a.scenario_id
    records = canonical_records(a)
    for row in records.values():
        for field in ("account_key", "counterparty_key", "customer_key", "reverses_key"):
            if row.get(field) is not None:
                assert row[field] in records
    origins = feature_origins(a)
    assert set(origins["fields"]) == set(AlertFeatures.model_fields)
    assert len(origins["fields"]) == 27
    assert all(
        f["input_origin"] == "declared_synthetic" and not f["transaction_derived"]
        for f in origins["fields"].values()
    )
    assert origins["observed_records"]
    assert AlertFeatures.model_validate(a.declarations)


@requires_dictionary
def test_hand_computed_concentration_related_flows_corrections_and_income():
    assert expected_activity(scenario_bundle("concentration"))["total"] == "10020"
    assert expected_activity(scenario_bundle("concentration"))["counterparties"] == {
        "account-counterparty": "10000",
        "account-secondary": "20",
    }
    flow = expected_activity(scenario_bundle("flow_change"))
    assert flow["incoming"] == "600" and flow["outgoing"] == "9000"
    related = expected_activity(scenario_bundle("related_transfers"))
    assert related["count"] == 12 and related["total"] == "3000"
    correction = scenario_bundle("corrections")
    assert expected_activity(correction)["count"] == 13
    assert expected_activity(correction, net=True)["count"] == 11
    assert scenario_bundle("missing_income").declarations["income"] is None
    assert scenario_bundle("zero_income").declarations["income"] == 0
    assert (
        feature_origins(scenario_bundle("missing_income"))["fields"]["income"]["origin"]
        == "unavailable"
    )
    assert (
        feature_origins(scenario_bundle("zero_income"))["fields"]["income"]["origin"]
        == "declared_synthetic"
    )
    assert expected_activity(scenario_bundle("incomplete_history"))["coverage"] == "partial"
    assert expected_activity(scenario_bundle("unknown_time"))["count"] == 11


@pytest.mark.parametrize(
    "key,seed", [("unknown", 1701), (True, 1701), ("ordinary", True), ("ordinary", -1)]
)
def test_invalid_catalog_selection_rejected(key, seed):
    with pytest.raises(EvidenceBlocked):
        scenario_bundle(key, seed)


@requires_dictionary
def test_preview_is_reproducible_and_does_not_manufacture_model_results():
    a = preview()
    assert a == preview() and len(a) == 16
    assert all("score" not in item and "job" not in item for item in a)
    for spec in CATALOG:
        expected = expected_activity(scenario_bundle(spec.key))
        assert Decimal(expected["total"]) == Decimal(expected["incoming"]) + Decimal(
            expected["outgoing"]
        )


def test_original_fourteen_profile_manifests_remain_byte_equivalent():
    # Captured independently from HEAD's unmodified generator before G1 acceptance.
    key = UUID("079f07bb-6bb5-478d-a497-7da1aa8f4e1e")
    profiles = [p for p in PROFILES if not p.startswith("g1_")]
    assert len(profiles) == 14
    actual = digest({p: bundle_manifest(generate_scenario(key, 17, p)) for p in profiles})
    assert actual == "427c766a75ddade411c43ef7a6d6ac65532907f349bd19cde7df66d391202eb9"


@pytest.mark.parametrize("corruption", ["missing", "modified"])
def test_feature_provenance_requires_actual_sha_verified_dictionary(monkeypatch, corruption):
    from pathlib import Path

    original = Path.read_bytes

    def changed(path):
        if path.name == "data_dictionary.csv":
            if corruption == "missing":
                raise FileNotFoundError()
            return b"untrusted metadata"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(EvidenceBlocked, match="approved_feature_dictionary_unavailable"):
        feature_origins(scenario_bundle("ordinary"))
