"""Full 4000-case SHAP identity replay against approved private extension outputs."""

import hashlib
import io
import json
import math
from dataclasses import dataclass

from trueflag_ml.explainability import MAX_EXPLANATION_BATCH, ExplanationService
from trueflag_ml.explanation_contract import (
    GROUP_ATOL,
    RECONSTRUCTION_ATOL,
    SCORE_ATOL,
    ExplanationVerificationError,
)
from trueflag_ml.explanation_reference import REFERENCE_FILES, reference_snapshots, strict_json
from trueflag_ml.loader import DEFAULT_ROOT
from trueflag_ml.regression import FEATURES_PATH, REFERENCE_SHA256, _verified_csv, load_evaluation
from trueflag_ml.trust import APPROVED_SHA256, CONTRACT_PATH, MODEL_PATH


@dataclass(frozen=True)
class ExplanationRegressionReport:
    matched_records: int
    verified_explanations: int
    unavailable: int
    mismatches: int
    maximum_reconstruction_residual: float
    maximum_model_score_difference: float
    maximum_reference_encoded_difference: float
    maximum_reference_grouped_difference: float
    maximum_reference_base_difference: float
    missing_income_records: int
    zero_income_records: int
    score_atol: float = SCORE_ATOL
    grouping_atol: float = GROUP_ATOL
    reconstruction_atol: float = RECONSTRUCTION_ATOL
    rtol: float = 0.0

    @property
    def passed(self):
        return (
            self.matched_records == self.verified_explanations == 4000
            and self.unavailable == self.mismatches == 0
        )


def require(condition, code):
    if not condition:
        raise ExplanationVerificationError(code)


def load_original_reference(expected_ids, fields, mapping):
    snapshots = reference_snapshots()
    metadata = strict_json(snapshots["metadata.json"])
    report = strict_json(snapshots["verification.json"])
    require(
        report["status"] == "PASS"
        and report["expected"] == report["passed"] == 4000
        and report["failed"] == 0,
        "original_verification_invalid",
    )
    require(
        report["payload_sha256"] == REFERENCE_FILES["explanations.jsonl"][0]
        and report["metadata_sha256"] == REFERENCE_FILES["metadata.json"][0],
        "original_verification_invalid",
    )
    require(
        metadata["fields"] == list(fields) and metadata["encoded_to_original"] == list(mapping),
        "original_mapping_invalid",
    )
    ids = metadata["ids"]
    require(
        len(ids) == len(set(ids)) == 4000 and set(ids) == set(expected_ids),
        "original_reference_ids_invalid",
    )
    core = {
        "model": APPROVED_SHA256[MODEL_PATH],
        "contract": APPROVED_SHA256[CONTRACT_PATH],
        "source": REFERENCE_SHA256[FEATURES_PATH],
        "predictions": REFERENCE_SHA256["validation/final_evaluation_predictions.csv"],
    }
    require(
        all(metadata["hashes"][k] == report["hashes"][k] == v for k, v in core.items()),
        "original_reference_identity_invalid",
    )
    require(
        metadata["generator_sha256"]
        == report["generator_sha256"]
        == "06d1e45815ec6daaf145b66c586139852d3c95d59477c0e8f8317f31daf2969a",
        "original_reference_identity_invalid",
    )
    lines = {}
    for line in io.BytesIO(snapshots["explanations.jsonl"]):
        record = strict_json(line)
        ident = record.get("technical_row_id")
        require(
            type(ident) is str and ident in expected_ids and ident not in lines,
            "original_reference_ids_invalid",
        )
        lines[ident] = line
    require(set(lines) == set(expected_ids), "original_reference_ids_invalid")
    return metadata, lines


def compare_original(result, record, original, raw, saved_score, metadata):
    require(result.status == "verified", "explanation_unavailable")
    require(
        original["technical_row_id"] == record.record_id == result.record_id
        and original["schema"] == "trueflag.explanations.v1",
        "original_reference_identity_invalid",
    )
    require(
        original["status"] in {"PASS", "GENERATED_PENDING_INDEPENDENT_VERIFICATION"}
        and original["failure_reason"] is None
        and original["hashes"] == metadata["hashes"],
        "original_reference_identity_invalid",
    )
    method = original["method"]
    require(
        method["positive_class"] == method["positive_class_index"] == 1
        and method["version"] == "0.51.0"
        and method["dependence"] == "tree_path_dependent"
        and method["model_output_argument"] == "raw"
        and method["output_space"] == "SAR-positive predict_proba score",
        "original_method_invalid",
    )
    old_hash = hashlib.sha256(
        json.dumps(
            {"technical_row_id": record.record_id, "fields": raw},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    require(original["input_sha256"] == old_hash, "original_input_mismatch")
    fields = original["fields"]
    require(
        [f["name"] for f in fields] == [f.name for f in result.features], "original_mapping_invalid"
    )
    encoded = original["encoded_contributions"]
    require(
        len(encoded) == 41 and all(type(v) is float and math.isfinite(v) for v in encoded),
        "original_contributions_invalid",
    )
    for old, current in zip(fields, result.features):
        value = raw[old["name"]]
        missing = value == "\\N"
        require(
            old["recorded_value"] == (None if missing else value)
            and old["missing"] == current.missing == missing
            and old["missing_code"] == ("\\N" if missing else None),
            "original_input_mismatch",
        )
        require(
            type(old["contribution"]) is float and math.isfinite(old["contribution"]),
            "original_contributions_invalid",
        )
        subtotal = math.fsum(
            v for v, name in zip(encoded, metadata["encoded_to_original"]) if name == old["name"]
        )
        require(abs(subtotal - old["contribution"]) <= GROUP_ATOL, "original_grouping_invalid")
    base, score = original["reference_score"], original["score"]
    require(
        type(base) is float
        and math.isfinite(base)
        and type(score) is float
        and math.isfinite(score)
        and 0 <= score <= 1,
        "original_contributions_invalid",
    )
    require(
        abs(base + math.fsum(encoded) - score) <= RECONSTRUCTION_ATOL
        and abs(score - saved_score) <= SCORE_ATOL,
        "original_reconstruction_invalid",
    )
    differences = (
        abs(result.model_score - saved_score),
        max(abs(a - b) for a, b in zip(result.encoded_contributions, encoded)),
        max(abs(a.contribution - b["contribution"]) for a, b in zip(result.features, fields)),
        abs(result.base_value - base),
    )
    require(list(result.top_features) == original["display"]["fields"], "original_ranking_mismatch")
    require(
        abs(result.other_features_contribution - original["display"]["other_fields_subtotal"])
        <= GROUP_ATOL,
        "original_ranking_mismatch",
    )
    return differences


def run_explanation_regression(progress=None):
    from app.schemas.alerts import AlertFeatures

    evaluation = load_evaluation()
    ids = frozenset(r.record_id for r in evaluation.records)
    service = ExplanationService(authorize=lambda ident: ident in ids)
    metadata, original_lines = load_original_reference(
        ids, tuple(AlertFeatures.model_fields), service.encoded_to_original
    )
    raw_rows = _verified_csv(DEFAULT_ROOT, FEATURES_PATH)
    raw = {
        r["technical_row_id"]: {name: r[name] for name in AlertFeatures.model_fields}
        for r in raw_rows
        if r["technical_row_id"] in ids
    }
    del raw_rows
    verified = unavailable = mismatches = 0
    maximum_residual = 0.0
    maximum = [0.0] * 4
    for start in range(0, len(evaluation.records), MAX_EXPLANATION_BATCH):
        records = evaluation.records[start : start + MAX_EXPLANATION_BATCH]
        results = service.explain_batch(records)
        require(
            len(results) == len(records)
            and [r.record_id for r in results] == [r.record_id for r in records],
            "explanation_result_ids_invalid",
        )
        for result, record in zip(results, records):
            if result.status != "verified":
                unavailable += 1
                continue
            verified += 1
            maximum_residual = max(maximum_residual, abs(result.reconstruction_residual))
            try:
                differences = compare_original(
                    result,
                    record,
                    strict_json(original_lines[record.record_id]),
                    raw[record.record_id],
                    evaluation.reference_scores[record.record_id],
                    metadata,
                )
                maximum = [max(a, b) for a, b in zip(maximum, differences)]
                mismatches += any(value > SCORE_ATOL for value in differences)
            except ExplanationVerificationError:
                mismatches += 1
        if progress and (start + len(records)) % 512 == 0:
            progress(start + len(records))
    return ExplanationRegressionReport(
        matched_records=len(evaluation.records),
        verified_explanations=verified,
        unavailable=unavailable,
        mismatches=mismatches,
        maximum_reconstruction_residual=maximum_residual,
        maximum_model_score_difference=maximum[0],
        maximum_reference_encoded_difference=maximum[1],
        maximum_reference_grouped_difference=maximum[2],
        maximum_reference_base_difference=maximum[3],
        missing_income_records=sum(r.features["income"] is None for r in evaluation.records),
        zero_income_records=sum(r.features["income"] == 0 for r in evaluation.records),
    )
