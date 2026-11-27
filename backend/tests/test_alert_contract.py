import copy
import csv
import hashlib
import json

import pytest
from conftest import BACKEND
from pydantic import ValidationError

from app.schemas.alerts import BASELINE_CONTRACT_SHA256, AlertFeatures, AlertIngestionInput
from app.services.ingestion import fingerprints


def test_contract_matches_staged_immutable_reference():
    path = BACKEND.parent / "assets/local/baseline/contracts/predictor_contract.json"
    if not path.is_file():
        pytest.skip("Optional private reference is not installed")
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == BASELINE_CONTRACT_SHA256
    contract = json.loads(content)
    assert list(AlertFeatures.model_fields) == contract["structured_predictors"]
    assert not set(AlertFeatures.model_fields) & set(contract["excluded_from_scorer"])


@pytest.mark.parametrize("income", [None, 0, 0.0, -10.5, 1e20])
def test_income_values_preserved_without_imputation(alert_payload, income):
    alert_payload["features"]["income"] = income
    value = AlertIngestionInput.model_validate(alert_payload).features.income
    assert value == income and type(value) is type(income)


def test_values_not_scaled_clamped_or_categorically_remapped(alert_payload):
    alert_payload["features"].update(
        state="new-category", totalSpend90d=-12.25, nbrPurchases90d=2**60 + 1
    )
    features = AlertIngestionInput.model_validate(alert_payload).features
    assert features.state == "new-category"
    assert features.totalSpend90d == -12.25
    assert features.nbrPurchases90d == 2**60 + 1
    assert type(features.nbrPurchases90d) is int


@pytest.mark.parametrize(
    "field,value",
    [
        ("income", True),
        ("income", "0"),
        ("income", "\\N"),
        ("income", float("nan")),
        ("income", float("inf")),
        ("income", float("-inf")),
        ("totalSpend90d", False),
        ("totalSpend90d", None),
        ("kycRiskScore", -1),
        ("kycRiskScore", 7),
        ("kycRiskScore", 3.5),
        ("kycRiskScore", True),
        ("state", 1),
        ("state", ""),
        ("state", "   "),
    ],
)
def test_invalid_feature_types_and_unsupported_kyc(alert_payload, field, value):
    alert_payload["features"][field] = value
    with pytest.raises(ValidationError):
        AlertIngestionInput.model_validate(alert_payload)


@pytest.mark.parametrize("field", ["income", "state", "PEP"])
def test_missing_field_is_not_filled(alert_payload, field):
    del alert_payload["features"][field]
    with pytest.raises(ValidationError):
        AlertIngestionInput.model_validate(alert_payload)


@pytest.mark.parametrize(
    "field",
    [
        "SAR",
        "csrNotes",
        "ALERT",
        "indCustReqRefund90d",
        "technical_row_id",
        "priority_group",
        "partition",
        "score",
    ],
)
def test_excluded_features_rejected(alert_payload, field):
    alert_payload["features"][field] = 1
    with pytest.raises(ValidationError):
        AlertIngestionInput.model_validate(alert_payload)


def test_hashes_ignore_key_order_and_equivalent_numeric_spelling(alert_payload):
    first = AlertIngestionInput.model_validate(alert_payload)
    equivalent = copy.deepcopy(alert_payload)
    equivalent["features"] = dict(reversed(list(equivalent["features"].items())))
    equivalent["features"].update(kycRiskScore=3.0, totalSpend90d=-0.0)
    assert fingerprints(first) == fingerprints(AlertIngestionInput.model_validate(equivalent))


def test_missing_and_zero_income_have_distinct_fingerprints(alert_payload):
    first = fingerprints(AlertIngestionInput.model_validate(alert_payload))
    alert_payload["features"]["income"] = 0
    assert first != fingerprints(AlertIngestionInput.model_validate(alert_payload))


def test_adjacent_large_integers_have_distinct_fingerprints(alert_payload):
    alert_payload["features"]["nbrPurchases90d"] = 2**60
    first = fingerprints(AlertIngestionInput.model_validate(alert_payload))
    alert_payload["features"]["nbrPurchases90d"] += 1
    assert first != fingerprints(AlertIngestionInput.model_validate(alert_payload))


def test_source_id_changes_request_hash_but_not_feature_hash(alert_payload):
    original = fingerprints(AlertIngestionInput.model_validate(alert_payload))
    alert_payload["source_id"] = "another-synthetic-alert"
    changed = fingerprints(AlertIngestionInput.model_validate(alert_payload))
    assert original[0] == changed[0] and original[1] != changed[1]


def test_staged_synthetic_records_fit_the_transport_contract():
    path = BACKEND.parent / "assets/local/baseline/data/datarobot_cleaned_v1.csv"
    if not path.is_file():
        pytest.skip("Optional private synthetic reference is not installed")
    checked = 0
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            features = {}
            for field in AlertFeatures.model_fields:
                raw = row[field]
                if field == "state":
                    value = raw
                elif field == "income" and raw == "\\N":
                    value = None
                else:
                    try:
                        value = int(raw)
                    except ValueError:
                        value = float(raw)
                features[field] = value
            # This checks only input representation; no source labels, DB writes or ML calls.
            try:
                validated = AlertFeatures.model_validate(features)
            except ValidationError:
                pytest.fail(
                    "Retained synthetic input fails contract validation; values withheld",
                    pytrace=False,
                )
            if validated.model_dump() != features:
                pytest.fail(
                    "Contract validation changed retained values; values withheld", pytrace=False
                )
            checked += 1
    assert checked == 10000
