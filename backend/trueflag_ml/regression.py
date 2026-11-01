"""Pinned 4000-score identity replay; aggregate output only, without policy execution."""

import csv
import hashlib
import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trueflag_ml.loader import DEFAULT_ROOT
from trueflag_ml.scoring import (
    MAX_BATCH_SIZE,
    RFScoringService,
    ScoreResult,
    ScoringInputError,
    ScoringRecord,
    validate_record_id,
)
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION

REFERENCE_PATH = "validation/final_evaluation_predictions.csv"
FEATURES_PATH = "data/datarobot_cleaned_v1.csv"
REFERENCE_SHA256 = MappingProxyType(
    {
        REFERENCE_PATH: "3803602f70fc5a1b31e5e38b7d7019ed034c85284853f18bd072558d71f004e2",
        FEATURES_PATH: "17244da02f7262bdf3c3b582671fa4d3675681489c1dfc23f1ae23e415da173f",
    }
)
EXPECTED_RECORDS = 4000
ABSOLUTE_TOLERANCE = 1e-12


class RegressionError(Exception):
    """Reason code only, without record IDs, feature values or private paths."""


@dataclass(frozen=True)
class EvaluationSet:
    records: tuple[ScoringRecord, ...]
    reference_scores: Mapping[str, float]


@dataclass(frozen=True)
class RegressionReport:
    matched_records: int
    scored_records: int
    maximum_absolute_error: float | None
    mismatches: int
    processing_failures: int
    absolute_tolerance: float = ABSOLUTE_TOLERANCE
    relative_tolerance: float = 0.0

    @property
    def passed(self):
        return self.mismatches == 0


def _verified_csv(root, relative):
    try:
        directory = Path(root).resolve(strict=True)
        path = (directory / relative).resolve(strict=True)
        if not path.is_relative_to(directory) or not path.is_file():
            raise RegressionError("reference_location_invalid")
        with path.open("rb") as stream:
            content = stream.read(64 * 1024 * 1024 + 1)
        if len(content) > 64 * 1024 * 1024:
            raise RegressionError("reference_integrity_failed")
        if hashlib.sha256(content).hexdigest() != REFERENCE_SHA256[relative]:
            raise RegressionError("reference_integrity_failed")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""), strict=True)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise RegressionError("reference_schema_invalid")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise RegressionError("reference_schema_invalid")
        return rows
    except FileNotFoundError:
        raise RegressionError("reference_missing") from None
    except OSError:
        raise RegressionError("reference_unreadable") from None
    except (UnicodeError, csv.Error):
        raise RegressionError("reference_schema_invalid") from None


def _aligned_rows(references, feature_rows, fields, expected_count):
    if len(references) != expected_count:
        raise RegressionError("reference_count_invalid")
    scores, labels = {}, {}
    for row in references:
        try:
            ident = row["technical_row_id"]
            validate_record_id(ident)
            if ident in scores:
                raise RegressionError("duplicate_reference_id")
            if row["model"] != "RF" or row["execution_status"] != "processed":
                raise RegressionError("reference_status_invalid")
            if row["SAR"] not in {"0", "1"}:
                raise RegressionError("reference_label_invalid")
            score = float(row["score"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise RegressionError("reference_score_invalid")
            scores[ident], labels[ident] = score, row["SAR"]
        except (KeyError, ValueError, TypeError, ScoringInputError):
            raise RegressionError("reference_schema_invalid") from None
    seen, selected = set(), {}
    for row in feature_rows:
        try:
            ident = row["technical_row_id"]
            validate_record_id(ident)
            if ident in seen:
                raise RegressionError("duplicate_feature_id")
            seen.add(ident)
            if ident in scores:
                if row["SAR"] != labels[ident]:
                    raise RegressionError("reference_label_mismatch")
                selected[ident] = {name: row[name] for name in fields}
        except (KeyError, TypeError, ScoringInputError):
            raise RegressionError("feature_schema_invalid") from None
    if set(selected) != set(scores):
        raise RegressionError("evaluation_ids_mismatch")
    return scores, [selected[ident] for ident in scores]


def load_evaluation(artifact_root: Path | None = None) -> EvaluationSet:
    import numpy as np
    import pandas as pd

    from app.schemas.alerts import AlertFeatures

    root = DEFAULT_ROOT if artifact_root is None else artifact_root
    references = _verified_csv(root, REFERENCE_PATH)
    feature_rows = _verified_csv(root, FEATURES_PATH)
    if len(feature_rows) != 10000:
        raise RegressionError("feature_count_invalid")
    fields = tuple(AlertFeatures.model_fields)
    scores, rows = _aligned_rows(references, feature_rows, fields, EXPECTED_RECORDS)
    try:
        frame = pd.DataFrame(rows, columns=fields)
        # Historical CSV transport only. Runtime scoring rejects numeric/missing-token strings.
        for field in fields:
            if field != "state":
                frame[field] = pd.to_numeric(frame[field].replace("\\N", np.nan), errors="raise")
        features = frame.to_dict(orient="records")
        for values in features:
            if pd.isna(values["income"]):
                values["income"] = None
            AlertFeatures.model_validate(values)
    except Exception:
        raise RegressionError("evaluation_features_invalid") from None
    records = tuple(ScoringRecord(ident, values) for ident, values in zip(scores, features))
    return EvaluationSet(records, MappingProxyType(scores))


def compare_results(reference_scores: Mapping[str, float], results) -> RegressionReport:
    if not reference_scores:
        raise RegressionError("reference_count_invalid")
    for ident, reference in reference_scores.items():
        try:
            validate_record_id(ident)
        except ScoringInputError:
            raise RegressionError("reference_schema_invalid") from None
        if (
            type(reference) not in (int, float)
            or not 0 <= reference <= 1
            or not math.isfinite(reference)
        ):
            raise RegressionError("reference_score_invalid")
    by_id = {}
    for result in results:
        if type(result) is not ScoreResult:
            raise RegressionError("result_schema_invalid")
        try:
            validate_record_id(result.record_id)
        except ScoringInputError:
            raise RegressionError("result_schema_invalid") from None
        if result.record_id in by_id:
            raise RegressionError("duplicate_result_id")
        by_id[result.record_id] = result
    if set(by_id) != set(reference_scores):
        raise RegressionError("result_ids_mismatch")
    errors, failures = [], 0
    for ident, reference in reference_scores.items():
        result = by_id[ident]
        if (
            result.model_version != MODEL_VERSION
            or result.model_sha256 != APPROVED_SHA256[MODEL_PATH]
            or type(result.positive_class_label) is not int
            or result.positive_class_label != 1
        ):
            raise RegressionError("result_model_mismatch")
        if (
            result.processing_status != "processed"
            or result.reason is not None
            or type(result.score) is not float
            or not math.isfinite(result.score)
            or not 0 <= result.score <= 1
        ):
            failures += 1
        else:
            errors.append(abs(result.score - reference))
    return RegressionReport(
        matched_records=len(by_id),
        scored_records=len(errors),
        maximum_absolute_error=max(errors) if errors else None,
        mismatches=failures + sum(error > ABSOLUTE_TOLERANCE for error in errors),
        processing_failures=failures,
    )


def score_evaluation(service, evaluation, batch_size=MAX_BATCH_SIZE):
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise RegressionError("regression_batch_invalid")
    results = []
    for start in range(0, len(evaluation.records), batch_size):
        results.extend(service.score_batch(evaluation.records[start : start + batch_size]))
    return compare_results(evaluation.reference_scores, results)


def run_regression(artifact_root: Path | None = None) -> RegressionReport:
    service = RFScoringService(artifact_root)
    return score_evaluation(service, load_evaluation(artifact_root))
