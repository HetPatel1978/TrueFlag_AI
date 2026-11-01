"""Authorization-gated exact TreeSHAP with fail-closed independent output verification."""

import importlib.metadata
import math
import warnings
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from trueflag_ml.explanation_contract import (
    SCORE_ATOL,
    ExplanationInputError,
    ExplanationLoadError,
    ExplanationResult,
    ExplanationVerificationError,
    FeatureContribution,
    input_digest,
)
from trueflag_ml.explanation_verification import independent_mapping, verify_explanation
from trueflag_ml.loader import load_approved_pipeline
from trueflag_ml.scoring import _SCORING_LOCK, RFScoringService, ScoringRecord, _validate_batch

MAX_EXPLANATION_BATCH = 64
EXPLANATION_VERSIONS = MappingProxyType(
    {
        "shap": "0.51.0",
        "numba": "0.68.1",
        "llvmlite": "0.50.0",
        "slicer": "0.0.8",
        "cloudpickle": "3.1.2",
    }
)


def verify_explanation_runtime():
    try:
        versions = {name: importlib.metadata.version(name) for name in EXPLANATION_VERSIONS}
    except importlib.metadata.PackageNotFoundError:
        raise ExplanationLoadError("explanation_dependency_missing") from None
    if versions != dict(EXPLANATION_VERSIONS):
        raise ExplanationLoadError("explanation_dependency_incompatible")


def encoded_feature_map(loaded):
    from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

    pre = loaded.pipeline.named_steps["preprocessor"]
    mapping = [None] * len(pre.get_feature_names_out())
    for name, transformer, columns in pre.transformers_:
        span = pre.output_indices_[name]
        if span.start == span.stop:
            continue
        if type(transformer) is OneHotEncoder:
            if (
                transformer.drop is not None
                or transformer.min_frequency is not None
                or transformer.max_categories is not None
            ):
                raise ExplanationLoadError("encoded_mapping_invalid")
            names = [
                field
                for field, categories in zip(columns, transformer.categories_)
                for _ in categories
            ]
        elif type(transformer) is FunctionTransformer and transformer.func is None:
            names = list(columns)
        else:
            raise ExplanationLoadError("encoded_mapping_invalid")
        if len(names) != span.stop - span.start:
            raise ExplanationLoadError("encoded_mapping_invalid")
        for position, field in zip(range(span.start, span.stop), names):
            if mapping[position] is not None:
                raise ExplanationLoadError("encoded_mapping_invalid")
            mapping[position] = field
    if (
        len(mapping) != 41
        or None in mapping
        or set(mapping) != set(loaded.fields)
        or tuple(mapping) != independent_mapping(loaded)
    ):
        raise ExplanationLoadError("encoded_mapping_invalid")
    return tuple(mapping)


def _validate_native_routing(forest, explainer):
    import numpy as np

    if len(explainer.model.trees) != len(forest.estimators_):
        raise ExplanationLoadError("native_routing_invalid")
    for actual, parsed in zip(forest.estimators_, explainer.model.trees):
        tree = actual.tree_
        wanted = np.where(tree.missing_go_to_left, tree.children_left, tree.children_right)
        if not np.array_equal(wanted, parsed.children_default):
            raise ExplanationLoadError("native_routing_invalid")


class ExplanationService:
    def __init__(self, authorize, artifact_root: Path | None = None):
        # Trusted host callback, checked for each case before work and again before disclosure.
        if not callable(authorize):
            raise ExplanationInputError("authorization_required")
        self._authorize = authorize
        self._loaded = load_approved_pipeline(artifact_root)
        self._scorer = RFScoringService(artifact_root)
        verify_explanation_runtime()
        try:
            import shap

            with _SCORING_LOCK, warnings.catch_warnings():
                warnings.simplefilter("error")
                self._mapping = encoded_feature_map(self._loaded)
                forest = self._loaded.pipeline.named_steps["estimator"]
                self._explainer = shap.TreeExplainer(
                    forest, feature_perturbation="tree_path_dependent", model_output="raw"
                )
                _validate_native_routing(forest, self._explainer)
        except ExplanationLoadError:
            raise
        except Exception:
            raise ExplanationLoadError("explanation_runtime_unavailable") from None

    def _allowed(self, ident):
        try:
            return self._authorize(ident) is True
        except Exception:
            return False

    @property
    def encoded_to_original(self):
        return self._mapping

    def _unavailable(self, ident, reason):
        return ExplanationResult(ident, "unavailable", reason=reason)

    def explain_one(self, record_id, features):
        return self.explain_batch([ScoringRecord(record_id, features)])[0]

    def explain_batch(self, records):
        records = _validate_batch(records)
        if len(records) > MAX_EXPLANATION_BATCH:
            raise ExplanationInputError("explanation_batch_invalid")
        import numpy as np
        import pandas as pd
        from pydantic import ValidationError
        from threadpoolctl import threadpool_limits

        from app.schemas.alerts import AlertFeatures

        output, snapshots, positions = [], [], []
        for position, record in enumerate(records):
            if not self._allowed(record.record_id):
                output.append(self._unavailable(record.record_id, "not_authorized"))
                continue
            try:
                if not isinstance(record.features, Mapping):
                    raise ValueError
                values = AlertFeatures.model_validate(dict(record.features)).model_dump()
                snapshot = ScoringRecord(record.record_id, MappingProxyType(values))
                input_digest(snapshot)
            except (ValidationError, ValueError, TypeError, OverflowError):
                output.append(self._unavailable(record.record_id, "invalid_features"))
                continue
            output.append(None)
            positions.append(position)
            snapshots.append(snapshot)
        if not snapshots:
            return tuple(output)
        try:
            with _SCORING_LOCK, threadpool_limits(limits=1), warnings.catch_warnings():
                warnings.simplefilter("error")
                scores = self._scorer.score_batch(snapshots)
                if any(score.processing_status != "processed" for score in scores):
                    raise ExplanationVerificationError("scoring_unavailable")
                frame = pd.concat(
                    [self._loaded.feature_frame(r.features) for r in snapshots], ignore_index=True
                )
                matrix = self._loaded.pipeline[:-1].transform(frame)
                direct = self._loaded.pipeline.predict_proba(frame)
                forest = self._loaded.pipeline.named_steps["estimator"]
                if tuple(forest.classes_) != (0, 1) or tuple(self._loaded.pipeline.classes_) != (
                    0,
                    1,
                ):
                    raise ExplanationVerificationError("explanation_class_invalid")
                _validate_native_routing(forest, self._explainer)
                internal = self._explainer.model.predict(matrix)
                reference = np.array([s.score for s in scores])
                if (
                    direct.shape != (len(snapshots), 2)
                    or internal.shape != direct.shape
                    or not np.allclose(internal, direct, atol=SCORE_ATOL, rtol=0)
                    or not np.allclose(direct[:, 1], reference, atol=SCORE_ATOL, rtol=0)
                ):
                    raise ExplanationVerificationError("explanation_score_mismatch")
                income_index = self._mapping.index("income")
                if not np.array_equal(np.isnan(matrix[:, income_index]), frame.income.isna()):
                    raise ExplanationVerificationError("missingness_mismatch")
                values = self._explainer.shap_values(
                    matrix, approximate=False, check_additivity=True
                )
                base = np.asarray(self._explainer.expected_value)
                if (
                    values.shape != (len(snapshots), 41, 2)
                    or base.shape != (2,)
                    or not np.isfinite(values).all()
                    or not np.isfinite(base).all()
                ):
                    raise ExplanationVerificationError("explanation_shape_invalid")
                # Check both classes to reject a swapped output axis, not only a scalar sum.
                if not np.allclose(
                    base + values.sum(axis=1), direct, atol=1e-6, rtol=0
                ) or not np.allclose(values[:, :, 0], -values[:, :, 1], atol=1e-12, rtol=0):
                    raise ExplanationVerificationError("explanation_class_invalid")
                for row, (position, record, score) in enumerate(zip(positions, snapshots, scores)):
                    try:
                        candidate = self._candidate(
                            record, score, values[row, :, 1], float(base[1])
                        )
                        result = verify_explanation(
                            candidate, record, score, self._loaded, self._mapping
                        )
                    except ExplanationVerificationError as error:
                        result = self._unavailable(record.record_id, str(error))
                    if not self._allowed(record.record_id):
                        result = self._unavailable(record.record_id, "not_authorized")
                    output[position] = result
        except (ExplanationVerificationError, ExplanationLoadError) as error:
            for position in positions:
                output[position] = self._unavailable(records[position].record_id, str(error))
        except Exception:
            for position in positions:
                output[position] = self._unavailable(
                    records[position].record_id, "explanation_failed"
                )
        return tuple(output)

    def _candidate(self, record, score, encoded, base):
        fields = self._loaded.fields
        grouped = [
            float(sum(value for value, field in zip(encoded, self._mapping) if field == name))
            for name in fields
        ]
        contributions = tuple(
            FeatureContribution(
                name,
                value,
                "raises_score" if value > 0 else "lowers_score" if value < 0 else "no_contribution",
                record.features[name] is None,
            )
            for name, value in zip(fields, grouped)
        )
        order = sorted(range(27), key=lambda j: (-abs(grouped[j]), j))
        active = [j for j in order if grouped[j] != 0]
        chosen = active[:2]
        if chosen:
            opposite = next(
                (j for j in active if j not in chosen and grouped[j] * grouped[chosen[0]] < 0), None
            )
            if opposite is not None:
                chosen.append(opposite)
        return ExplanationResult(
            record.record_id,
            "pending_verification",
            input_sha256=input_digest(record),
            model_score=score.score,
            base_value=base,
            encoded_contributions=tuple(float(v) for v in encoded),
            features=contributions,
            ranking=tuple(fields[j] for j in order),
            top_features=tuple(fields[j] for j in chosen),
            other_features_contribution=float(
                sum(v for j, v in enumerate(grouped) if j not in chosen)
            ),
            reconstruction_residual=float(base + math.fsum(grouped) - score.score),
        )
