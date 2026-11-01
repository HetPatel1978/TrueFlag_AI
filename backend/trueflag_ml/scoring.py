"""Bounded, read-only scoring through the approved full RF pipeline; no HTTP or routing."""

import re
import threading
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from trueflag_ml.loader import ModelLoadError, load_approved_pipeline

MAX_BATCH_SIZE = 1000
POSITIVE_CLASS_LABEL = 1  # Original research target: integer SAR; never a crime determination.
_RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)
# threadpool_limits and warning filters affect process state on CPython 3.11.
_SCORING_LOCK = threading.RLock()


class ScoringInputError(Exception):
    """Sanitized batch/envelope rejection before inference; no submitted values in messages."""


@dataclass(frozen=True)
class ScoringRecord:
    record_id: str
    features: Mapping


@dataclass(frozen=True)
class ScoreResult:
    record_id: str
    score: float | None
    model_version: str
    model_sha256: str
    processing_status: Literal["processed", "failed"]
    reason: str | None = None
    positive_class_label: int = POSITIVE_CLASS_LABEL


def validate_record_id(value):
    if type(value) is not str or _RECORD_ID.fullmatch(value) is None:
        raise ScoringInputError("record_id_invalid")


def _validate_batch(records):
    if (
        not isinstance(records, Sequence)
        or isinstance(records, (str, bytes))
        or not 1 <= len(records) <= MAX_BATCH_SIZE
    ):
        raise ScoringInputError("batch_invalid")
    records = tuple(records)
    if not 1 <= len(records) <= MAX_BATCH_SIZE:
        raise ScoringInputError("batch_invalid")
    seen = set()
    for record in records:
        if type(record) is not ScoringRecord:
            raise ScoringInputError("batch_invalid")
        validate_record_id(record.record_id)
        if record.record_id in seen:
            raise ScoringInputError("duplicate_record_id")
        seen.add(record.record_id)
    return records


class RFScoringService:
    def __init__(self, artifact_root: Path | None = None):
        # Missing/incompatible assets fail service initialization with ModelLoadError.
        # No injected estimator, filename, uploaded bytes or expected-hash argument exists.
        self._loaded = load_approved_pipeline(artifact_root)
        self._classes = tuple(self._loaded.pipeline.classes_)
        self._positive_column = self._classes.index(POSITIVE_CLASS_LABEL)

    def _result(self, record_id, score=None, reason=None):
        return ScoreResult(
            record_id=record_id,
            score=score,
            model_version=self._loaded.model_version,
            model_sha256=self._loaded.model_sha256,
            processing_status="processed" if reason is None else "failed",
            reason=reason,
        )

    def score_one(self, record_id: str, features: Mapping) -> ScoreResult:
        return self.score_batch([ScoringRecord(record_id, features)])[0]

    def score_batch(self, records: Sequence[ScoringRecord]) -> tuple[ScoreResult, ...]:
        records = _validate_batch(records)
        import numpy as np
        import pandas as pd
        from threadpoolctl import threadpool_limits

        results, frames, positions = [], [], []
        for position, record in enumerate(records):
            try:
                if not isinstance(record.features, Mapping):
                    raise ModelLoadError("feature_input_invalid")
                frame = self._loaded.feature_frame(record.features)
            except ModelLoadError:
                results.append(self._result(record.record_id, reason="invalid_features"))
                continue
            frames.append(frame)
            positions.append(position)
            results.append(None)
        if not positions:
            return tuple(results)

        failure = None
        try:
            # Full original fitted pipeline only; no fitting, manual encoding or calibration.
            with _SCORING_LOCK, threadpool_limits(limits=1), warnings.catch_warnings():
                warnings.simplefilter("error")
                if tuple(self._loaded.pipeline.classes_) != self._classes:
                    failure = "model_state_invalid"
                else:
                    frame = pd.concat(frames, ignore_index=True)
                    probabilities = self._loaded.pipeline.predict_proba(frame)
                    if (
                        type(probabilities) is not np.ndarray
                        or probabilities.shape != (len(positions), len(self._classes))
                        or probabilities.dtype.kind != "f"
                    ):
                        failure = "invalid_model_output"
        except Exception:
            failure = "inference_failed"

        if failure:
            for position in positions:
                results[position] = self._result(records[position].record_id, reason=failure)
        else:
            for position, probabilities_row in zip(positions, probabilities):
                if (
                    not np.isfinite(probabilities_row).all()
                    or (probabilities_row < 0).any()
                    or (probabilities_row > 1).any()
                    or not np.isclose(probabilities_row.sum(), 1.0, atol=1e-12, rtol=0)
                ):
                    results[position] = self._result(
                        records[position].record_id, reason="invalid_model_output"
                    )
                else:
                    results[position] = self._result(
                        records[position].record_id, float(probabilities_row[self._positive_column])
                    )
        return tuple(results)
