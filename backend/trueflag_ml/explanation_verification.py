"""Independent contract/score/grouping/root-base checks; no generator validation is imported."""

import math
from dataclasses import replace

from trueflag_ml.explanation_contract import (
    GROUP_ATOL,
    INPUT_HASH_SCHEMA,
    RECONSTRUCTION_ATOL,
    SCORE_ATOL,
    ExplanationMethod,
    ExplanationResult,
    ExplanationVerificationError,
    FeatureContribution,
    input_digest,
)
from trueflag_ml.scoring import ScoreResult, ScoringRecord, validate_record_id
from trueflag_ml.trust import APPROVED_SHA256, CONTRACT_PATH, MODEL_PATH, MODEL_VERSION


def _require(condition, code):
    if not condition:
        raise ExplanationVerificationError(code)


def independent_mapping(loaded):
    # Derive by encoded labels, independently of the generator's category/slice expansion.
    names = loaded.pipeline.named_steps["preprocessor"].get_feature_names_out()
    mapping = []
    for name in names:
        prefix, _, suffix = name.partition("__")
        candidates = [
            field
            for field in loaded.fields
            if (prefix == "numeric" and suffix == field)
            or (prefix == "categories" and suffix.startswith(field + "_"))
        ]
        _require(len(candidates) == 1, "encoded_mapping_invalid")
        mapping.append(candidates[0])
    _require(len(mapping) == 41 and set(mapping) == set(loaded.fields), "encoded_mapping_invalid")
    _require(mapping.count("income") == 1, "encoded_mapping_invalid")
    return tuple(mapping)


def independent_base(loaded):
    forest = loaded.pipeline.named_steps["estimator"]
    positive = list(forest.classes_).index(1)
    # RF averages class proportions at each fitted root; no background data or fitting.
    probabilities = [
        float(t.tree_.value[0, 0, positive]) / math.fsum(t.tree_.value[0, 0])
        for t in forest.estimators_
    ]
    return math.fsum(probabilities) / len(probabilities)


def verify_explanation(result, record, scoring_result, loaded, expected_mapping):
    try:
        from app.schemas.alerts import AlertFeatures

        _require(
            type(record) is ScoringRecord and type(scoring_result) is ScoreResult,
            "explanation_input_invalid",
        )
        validate_record_id(record.record_id)
        AlertFeatures.model_validate(dict(record.features))
        _require(
            type(result) is ExplanationResult
            and result.status in {"pending_verification", "verified"}
            and result.reason is None,
            "explanation_status_invalid",
        )
        _require(
            result.record_id == record.record_id == scoring_result.record_id,
            "explanation_identity_invalid",
        )
        _require(
            result.model_version
            == scoring_result.model_version
            == loaded.model_version
            == MODEL_VERSION
            and result.model_sha256
            == scoring_result.model_sha256
            == loaded.model_sha256
            == APPROVED_SHA256[MODEL_PATH]
            and result.contract_sha256 == loaded.contract_sha256 == APPROVED_SHA256[CONTRACT_PATH],
            "explanation_identity_invalid",
        )
        _require(
            result.input_hash_schema == INPUT_HASH_SCHEMA
            and result.input_sha256 == input_digest(record),
            "explanation_input_mismatch",
        )
        _require(
            type(result.method) is ExplanationMethod and result.method == ExplanationMethod(),
            "explanation_method_invalid",
        )
        _require(
            type(result.method.positive_class_label) is int
            and type(result.method.positive_class_index) is int
            and result.method.approximate is False,
            "explanation_method_invalid",
        )
        _require(
            tuple(loaded.pipeline.classes_) == (0, 1)
            and tuple(loaded.pipeline.named_steps["estimator"].classes_) == (0, 1),
            "explanation_class_invalid",
        )
        _require(
            scoring_result.processing_status == "processed"
            and scoring_result.reason is None
            and type(scoring_result.positive_class_label) is int
            and scoring_result.positive_class_label == 1,
            "explanation_score_invalid",
        )
        _require(
            type(result.model_score) is float
            and math.isfinite(result.model_score)
            and 0 <= result.model_score <= 1,
            "explanation_score_invalid",
        )
        _require(
            type(scoring_result.score) is float
            and math.isfinite(scoring_result.score)
            and 0 <= scoring_result.score <= 1
            and abs(result.model_score - scoring_result.score) <= SCORE_ATOL,
            "explanation_score_mismatch",
        )
        _require(
            type(result.base_value) is float
            and math.isfinite(result.base_value)
            and abs(result.base_value - independent_base(loaded)) <= SCORE_ATOL,
            "explanation_base_mismatch",
        )
        mapping = independent_mapping(loaded)
        _require(mapping == tuple(expected_mapping), "encoded_mapping_invalid")
        encoded = result.encoded_contributions
        _require(
            len(encoded) == 41 and all(type(v) is float and math.isfinite(v) for v in encoded),
            "encoded_contributions_invalid",
        )
        _require(
            len(result.features) == 27 and tuple(f.name for f in result.features) == loaded.fields,
            "feature_contributions_invalid",
        )
        grouped = []
        for feature in result.features:
            _require(
                type(feature) is FeatureContribution
                and type(feature.contribution) is float
                and math.isfinite(feature.contribution),
                "feature_contributions_invalid",
            )
            contribution = math.fsum(
                value for value, name in zip(encoded, mapping) if name == feature.name
            )
            _require(
                abs(feature.contribution - contribution) <= GROUP_ATOL,
                "explanation_grouping_mismatch",
            )
            expected_direction = (
                "raises_score"
                if feature.contribution > 0
                else "lowers_score"
                if feature.contribution < 0
                else "no_contribution"
            )
            _require(
                feature.direction == expected_direction
                and type(feature.missing) is bool
                and feature.missing == (record.features[feature.name] is None),
                "feature_state_mismatch",
            )
            grouped.append(feature.contribution)
        total = math.fsum(grouped)
        _require(
            abs(result.base_value + total - result.model_score) <= RECONSTRUCTION_ATOL
            and abs(result.base_value + math.fsum(encoded) - result.model_score)
            <= RECONSTRUCTION_ATOL,
            "explanation_reconstruction_mismatch",
        )
        _require(
            type(result.reconstruction_residual) is float
            and math.isfinite(result.reconstruction_residual)
            and abs(
                result.reconstruction_residual - (result.base_value + total - result.model_score)
            )
            <= GROUP_ATOL,
            "explanation_reconstruction_mismatch",
        )
        order = sorted(range(27), key=lambda j: (-abs(grouped[j]), j))
        _require(
            result.ranking == tuple(loaded.fields[j] for j in order), "explanation_ranking_mismatch"
        )
        active = [j for j in order if grouped[j] != 0]
        chosen = active[:2]
        if chosen:
            opposite = next(
                (j for j in active if j not in chosen and grouped[j] * grouped[chosen[0]] < 0), None
            )
            if opposite is not None:
                chosen.append(opposite)
        _require(
            result.top_features == tuple(loaded.fields[j] for j in chosen),
            "explanation_ranking_mismatch",
        )
        other = math.fsum(value for j, value in enumerate(grouped) if j not in chosen)
        _require(
            type(result.other_features_contribution) is float
            and math.isfinite(result.other_features_contribution)
            and abs(result.other_features_contribution - other) <= GROUP_ATOL,
            "explanation_ranking_mismatch",
        )
        return replace(result, status="verified")
    except ExplanationVerificationError:
        raise
    except Exception:
        raise ExplanationVerificationError("explanation_payload_invalid") from None
