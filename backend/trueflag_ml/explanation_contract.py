"""Explanation data/provenance contracts; no model loading, authorization or SHAP execution."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from trueflag_ml.trust import APPROVED_SHA256, CONTRACT_PATH, MODEL_PATH, MODEL_VERSION

SCORE_ATOL = 1e-12
GROUP_ATOL = 1e-12
RECONSTRUCTION_ATOL = 1e-6
INPUT_HASH_SCHEMA = "trueflag.explanation-input.rational.v1"


class ExplanationInputError(Exception):
    """Sanitized request/envelope failure."""


class ExplanationLoadError(Exception):
    """Sanitized dependency/model/explainer initialization failure."""


class ExplanationVerificationError(Exception):
    """Sanitized failed independent verification."""


@dataclass(frozen=True)
class ExplanationMethod:
    algorithm: str = "Exact TreeSHAP"
    library_version: str = "0.51.0"
    feature_perturbation: str = "tree_path_dependent"
    model_output_argument: str = "raw"
    output_space: str = "SAR-positive predict_proba score"
    positive_class_label: int = 1
    positive_class_index: int = 1
    approximate: bool = False
    background: str = "fitted_tree_path_counts"


@dataclass(frozen=True)
class FeatureContribution:
    name: str
    contribution: float
    direction: Literal["raises_score", "lowers_score", "no_contribution"]
    missing: bool


@dataclass(frozen=True)
class ExplanationResult:
    record_id: str
    status: Literal["pending_verification", "verified", "unavailable"]
    reason: str | None = None
    input_sha256: str | None = None
    model_score: float | None = None
    base_value: float | None = None
    encoded_contributions: tuple[float, ...] = ()
    features: tuple[FeatureContribution, ...] = ()
    ranking: tuple[str, ...] = ()
    top_features: tuple[str, ...] = ()
    other_features_contribution: float | None = None
    reconstruction_residual: float | None = None
    model_version: str = MODEL_VERSION
    model_sha256: str = APPROVED_SHA256[MODEL_PATH]
    contract_sha256: str = APPROVED_SHA256[CONTRACT_PATH]
    input_hash_schema: str = INPUT_HASH_SCHEMA
    method: ExplanationMethod = ExplanationMethod()


def input_digest(record):
    # Same exact numeric equivalence as ingestion, separately named and bound to record identity.
    values = {}
    for name, value in record.features.items():
        if type(value) in (int, float):
            numerator, denominator = (value, 1) if type(value) is int else value.as_integer_ratio()
            value = {"numerator": str(numerator), "denominator": str(denominator)}
        values[name] = value
    payload = {"schema": INPUT_HASH_SCHEMA, "record_id": record.record_id, "features": values}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
