"""Actual RF/SHAP verification, adversarial payload checks and fail-closed authorization."""

import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from test_loader import HAS_REAL_RUNTIME, synthetic  # noqa: E402

from trueflag_ml import explainability, explanation_reference  # noqa: E402
from trueflag_ml.explanation_contract import (  # noqa: E402
    ExplanationInputError,
    ExplanationLoadError,
    ExplanationVerificationError,
    input_digest,
)
from trueflag_ml.explanation_regression import compare_original, load_original_reference  # noqa: E402
from trueflag_ml.explanation_verification import (  # noqa: E402
    independent_base,
    independent_mapping,
    verify_explanation,
)
from trueflag_ml.loader import DEFAULT_ROOT, ModelLoadError  # noqa: E402
from trueflag_ml.regression import FEATURES_PATH, _verified_csv, load_evaluation  # noqa: E402
from trueflag_ml.scoring import ScoringInputError, ScoringRecord  # noqa: E402

# Windows Application Control blocks the pinned llvmlite DLL on the current host.
# Real acceptance runs on Linux; an explicit flag can require a future Windows recheck.
HAS_SHAP_RUNTIME = (
    HAS_REAL_RUNTIME
    and importlib.util.find_spec("shap") is not None
    and (sys.platform != "win32" or os.environ.get("TRUEFLAG_REQUIRE_SHAP") == "1")
)


class ExplanationBoundaryTests(unittest.TestCase):
    def test_authorization_callback_is_required_before_model_loading(self):
        for callback in [None, True, False, "allow", {}, []]:
            with self.assertRaisesRegex(ExplanationInputError, "authorization_required"):
                explainability.ExplanationService(callback)

    def test_invalid_batch_envelope_fails_before_dependencies(self):
        service = object.__new__(explainability.ExplanationService)
        with self.assertRaisesRegex(ScoringInputError, "batch_invalid"):
            service.explain_batch([])

    def test_duplicate_ids_fail_before_dependencies(self):
        service = object.__new__(explainability.ExplanationService)
        with self.assertRaisesRegex(ScoringInputError, "duplicate_record_id"):
            service.explain_batch([ScoringRecord("same", {}), ScoringRecord("same", {})])

    def test_explanation_batch_has_a_stricter_cpu_bound(self):
        service = object.__new__(explainability.ExplanationService)
        records = [ScoringRecord(f"r{i}", {}) for i in range(65)]
        with self.assertRaisesRegex(ExplanationInputError, "explanation_batch_invalid"):
            service.explain_batch(records)

    def test_model_missing_fails_safely(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ModelLoadError, "artifact_missing"):
                explainability.ExplanationService(lambda _: True, Path(name))

    def test_unapproved_artifact_cannot_be_deserialized_by_explanation_service(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "model/selected_pipeline.joblib"
            path.parent.mkdir()
            path.write_bytes(b"unapproved pickle")
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                explainability.ExplanationService(lambda _: True, Path(name))

    def test_missing_explanation_dependency_is_sanitized(self):
        with patch.object(
            explainability.importlib.metadata,
            "version",
            side_effect=importlib.metadata.PackageNotFoundError("private-marker"),
        ):
            with self.assertRaisesRegex(ExplanationLoadError, "explanation_dependency_missing"):
                explainability.verify_explanation_runtime()

    def test_explanation_dependency_versions_are_exact(self):
        with patch.object(explainability.importlib.metadata, "version", return_value="0.0.0"):
            with self.assertRaisesRegex(
                ExplanationLoadError, "explanation_dependency_incompatible"
            ):
                explainability.verify_explanation_runtime()

    def test_input_hash_preserves_missing_vs_zero(self):
        self.assertNotEqual(
            input_digest(ScoringRecord("r", synthetic())),
            input_digest(ScoringRecord("r", synthetic(0))),
        )

    def test_input_hash_preserves_identity_and_normalizes_numeric_equivalence(self):
        self.assertEqual(
            input_digest(ScoringRecord("r", synthetic(0))),
            input_digest(ScoringRecord("r", synthetic(0.0))),
        )
        self.assertNotEqual(
            input_digest(ScoringRecord("r1", synthetic())),
            input_digest(ScoringRecord("r2", synthetic())),
        )

    def test_input_hash_does_not_depend_on_mapping_order(self):
        values = synthetic()
        self.assertEqual(
            input_digest(ScoringRecord("r", values)),
            input_digest(ScoringRecord("r", dict(reversed(list(values.items()))))),
        )

    def test_reference_missing_fails_safely(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(
                ExplanationVerificationError, "explanation_reference_missing"
            ):
                explanation_reference.reference_snapshots(Path(name))

    def test_reference_tampering_is_rejected_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as name:
            (Path(name) / "explanations.jsonl").write_bytes(b"malformed reference")
            with self.assertRaisesRegex(
                ExplanationVerificationError, "explanation_reference_integrity_failed"
            ):
                explanation_reference.reference_snapshots(Path(name))

    def test_nonfinite_and_malformed_reference_json_is_rejected(self):
        for value in [b'{"value":NaN}', b'{"value":Infinity}', b"private-marker", b"\xff"]:
            with self.assertRaisesRegex(
                ExplanationVerificationError, "explanation_reference_schema_invalid"
            ):
                explanation_reference.strict_json(value)


@unittest.skipUnless(
    HAS_SHAP_RUNTIME,
    "Actual SHAP acceptance requires private artifacts and the usable Linux runtime",
)
class ActualExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation = load_evaluation()
        chosen = list(cls.evaluation.records[:4])
        for predicate in [
            lambda r: r.features["income"] is None,
            lambda r: r.features["income"] == 0,
        ]:
            record = next(r for r in cls.evaluation.records if predicate(r))
            if record not in chosen:
                chosen.append(record)
        cls.records = tuple(chosen)
        cls.allowed = frozenset(r.record_id for r in cls.evaluation.records) | {
            "synthetic-missing",
            "synthetic-zero",
        }
        cls.service = explainability.ExplanationService(lambda ident: ident in cls.allowed)
        cls.results = cls.service.explain_batch(cls.records)
        if any(r.status != "verified" for r in cls.results):
            raise AssertionError("Real SHAP explanation failed independent verification")
        cls.scores = cls.service._scorer.score_batch(cls.records)

    def verify(self, candidate, record=None, scoring_result=None):
        return verify_explanation(
            candidate,
            record or self.records[0],
            scoring_result or self.scores[0],
            self.service._loaded,
            self.service.encoded_to_original,
        )

    def unavailable(self, result):
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.model_score)
        self.assertIsNone(result.base_value)
        self.assertEqual(result.features, ())
        self.assertEqual(result.encoded_contributions, ())
        self.assertEqual(result.ranking, ())

    def test_real_forest_output_is_positive_probability_with_41_to_27_mapping(self):
        for result, score in zip(self.results, self.scores):
            self.assertEqual(result.status, "verified")
            self.assertEqual(result.model_score, score.score)
            self.assertEqual(len(result.encoded_contributions), 41)
            self.assertEqual(len(result.features), 27)
            self.assertEqual(result.method.output_space, "SAR-positive predict_proba score")
            self.assertEqual(result.method.positive_class_index, 1)
            self.assertEqual(result.method.positive_class_label, 1)

    def test_independent_mapping_and_weighted_root_base_match(self):
        self.assertEqual(
            self.service.encoded_to_original, independent_mapping(self.service._loaded)
        )
        base = independent_base(self.service._loaded)
        self.assertTrue(all(abs(r.base_value - base) <= 1e-12 for r in self.results))
        self.assertEqual(self.service.encoded_to_original.count("state"), 9)
        self.assertEqual(self.service.encoded_to_original.count("kycRiskScore"), 7)
        self.assertEqual(self.service.encoded_to_original.count("income"), 1)

    def test_grouped_and_encoded_contributions_reconstruct_the_same_score(self):
        for result in self.results:
            for feature in result.features:
                total = math.fsum(
                    v
                    for v, name in zip(
                        result.encoded_contributions, self.service.encoded_to_original
                    )
                    if name == feature.name
                )
                self.assertLessEqual(abs(total - feature.contribution), 1e-12)
            self.assertLessEqual(
                abs(
                    result.base_value + math.fsum(result.encoded_contributions) - result.model_score
                ),
                1e-6,
            )
            self.assertLessEqual(
                abs(
                    result.base_value
                    + math.fsum(f.contribution for f in result.features)
                    - result.model_score
                ),
                1e-6,
            )

    def test_ranking_is_stable_absolute_magnitude_with_direction(self):
        for result in self.results:
            by_name = {f.name: f for f in result.features}
            magnitudes = [abs(by_name[name].contribution) for name in result.ranking]
            self.assertEqual(magnitudes, sorted(magnitudes, reverse=True))
            for feature in result.features:
                direction = (
                    "raises_score"
                    if feature.contribution > 0
                    else "lowers_score"
                    if feature.contribution < 0
                    else "no_contribution"
                )
                self.assertEqual(feature.direction, direction)

    def test_output_contains_no_recorded_feature_values_or_target(self):
        for result in self.results:
            value = asdict(result)
            self.assertNotIn("SAR", [f["name"] for f in value["features"]])
            self.assertNotIn("csrNotes", json.dumps(value))
            self.assertTrue(
                all(
                    set(f) == {"name", "contribution", "direction", "missing"}
                    for f in value["features"]
                )
            )
            self.assertEqual(json.loads(json.dumps(value, allow_nan=False))["status"], "verified")

    def test_single_batch_repeated_and_reordered_explanations_are_stable(self):
        repeated = self.service.explain_batch(self.records)
        singles = tuple(self.service.explain_one(r.record_id, r.features) for r in self.records)
        reordered = tuple(reversed(self.service.explain_batch(tuple(reversed(self.records)))))
        for result_set in [repeated, singles, reordered]:
            for expected, actual in zip(self.results, result_set):
                self.assertEqual(expected.input_sha256, actual.input_sha256)
                self.assertEqual(expected.ranking, actual.ranking)
                self.assertLessEqual(
                    max(
                        abs(a - b)
                        for a, b in zip(
                            expected.encoded_contributions, actual.encoded_contributions
                        )
                    ),
                    1e-12,
                )

    def test_missing_income_and_zero_remain_distinct(self):
        records = [
            ScoringRecord("synthetic-missing", synthetic()),
            ScoringRecord("synthetic-zero", synthetic(0)),
        ]
        results = self.service.explain_batch(records)
        self.assertTrue(all(r.status == "verified" for r in results))
        income = [next(f for f in r.features if f.name == "income") for r in results]
        self.assertTrue(income[0].missing)
        self.assertFalse(income[1].missing)
        self.assertNotEqual(results[0].input_sha256, results[1].input_sha256)

    def test_new_authorized_unknown_state_works_without_ui_population(self):
        result = self.service.explain_one(
            "synthetic-zero", {**synthetic(0), "state": "__new_category__"}
        )
        self.assertEqual(result.status, "verified")

    def test_authorization_denial_happens_before_validation_scoring_or_shap(self):
        with (
            patch.object(self.service, "_authorize", return_value=False),
            patch.object(
                self.service._scorer, "score_batch", side_effect=AssertionError("must not score")
            ) as blocked,
        ):
            result = self.service.explain_one(
                self.records[0].record_id, {"private-marker": "must not read"}
            )
        blocked.assert_not_called()
        self.unavailable(result)
        self.assertEqual(result.reason, "not_authorized")

    def test_authorization_requires_explicit_true_and_sanitizes_exceptions(self):
        for callback in [lambda _: 1, lambda _: False, lambda _: None]:
            with patch.object(self.service, "_authorize", callback):
                result = self.service.explain_one(
                    self.records[0].record_id, self.records[0].features
                )
            self.unavailable(result)
            self.assertEqual(result.reason, "not_authorized")
        with patch.object(self.service, "_authorize", side_effect=RuntimeError("private-marker")):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertNotIn("private-marker", repr(result))

    def test_revocation_during_computation_prevents_disclosure(self):
        with patch.object(self.service, "_authorize", side_effect=[True, False]):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertEqual(result.reason, "not_authorized")

    def test_mixed_batch_does_not_disclose_unowned_record(self):
        batch = [self.records[0], ScoringRecord("not-owned", {"SAR": "private-marker"})]
        results = self.service.explain_batch(batch)
        self.assertEqual(results[0].status, "verified")
        self.unavailable(results[1])
        self.assertNotIn("private-marker", repr(results[1]))

    def test_invalid_features_fail_without_misleading_partial_explanation(self):
        for values in [
            {},
            None,
            {**synthetic(), "SAR": 1},
            {**synthetic(), "income": "0"},
            {**synthetic(), "income": float("nan")},
            {**synthetic(), "kycRiskScore": True},
        ]:
            result = self.service.explain_one("synthetic-missing", values)
            self.unavailable(result)
            self.assertEqual(result.reason, "invalid_features")

    def test_scoring_failure_does_not_create_an_explanation(self):
        failed = replace(
            self.scores[0], score=None, processing_status="failed", reason="private-marker"
        )
        with patch.object(self.service._scorer, "score_batch", return_value=(failed,)):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertEqual(result.reason, "scoring_unavailable")
        self.assertNotIn("private-marker", repr(result))

    def test_shap_exception_and_warning_are_sanitized(self):
        def warning(*args, **kwargs):
            warnings.warn("private-marker", UserWarning)

        for effect in [RuntimeError("private-marker"), warning]:
            output = io.StringIO()
            with (
                redirect_stdout(output),
                redirect_stderr(output),
                patch.object(self.service._explainer, "shap_values", side_effect=effect),
            ):
                result = self.service.explain_one(
                    self.records[0].record_id, self.records[0].features
                )
            self.unavailable(result)
            self.assertNotIn("private-marker", repr(result) + output.getvalue())

    def test_invalid_shap_shape_or_nonfinite_values_fail(self):
        import numpy as np

        for values in [
            np.zeros((1, 40, 2)),
            np.full((1, 41, 2), np.nan),
            np.full((1, 41, 2), np.inf),
        ]:
            with patch.object(self.service._explainer, "shap_values", return_value=values):
                result = self.service.explain_one(
                    self.records[0].record_id, self.records[0].features
                )
            self.unavailable(result)

    def test_wrong_class_axis_is_rejected(self):
        record = self.records[0]
        matrix = self.service._loaded.pipeline[:-1].transform(
            self.service._loaded.feature_frame(record.features)
        )
        actual = self.service._explainer.shap_values(
            matrix, approximate=False, check_additivity=True
        )
        with patch.object(self.service._explainer, "shap_values", return_value=actual[:, :, ::-1]):
            result = self.service.explain_one(record.record_id, record.features)
        self.unavailable(result)

    def test_native_missing_routing_mismatch_is_rejected(self):
        parsed = self.service._explainer.model.trees[0]
        changed = parsed.children_default.copy()
        changed[0] = -999
        with patch.object(parsed, "children_default", changed):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertEqual(result.reason, "native_routing_invalid")

    def test_shap_internal_score_mismatch_is_rejected(self):
        import numpy as np

        with patch.object(
            self.service._explainer.model, "predict", return_value=np.array([[0.5, 0.5]])
        ):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertEqual(result.reason, "explanation_score_mismatch")

    def test_generator_grouping_tampering_never_returns_verified(self):
        original = self.service._candidate

        def tampered(*args):
            candidate = original(*args)
            feature = replace(
                candidate.features[0], contribution=candidate.features[0].contribution + 0.01
            )
            return replace(candidate, features=(feature, *candidate.features[1:]))

        with patch.object(self.service, "_candidate", side_effect=tampered):
            result = self.service.explain_one(self.records[0].record_id, self.records[0].features)
        self.unavailable(result)
        self.assertEqual(result.reason, "explanation_grouping_mismatch")

    def test_independent_verifier_rejects_identity_input_class_and_score_tampering(self):
        original = self.results[0]
        mutations = [
            replace(original, model_sha256="0" * 64),
            replace(original, contract_sha256="0" * 64),
            replace(original, record_id="other"),
            replace(original, input_sha256="0" * 64),
            replace(original, input_hash_schema="old-lexeme-schema"),
            replace(original, method=replace(original.method, positive_class_index=0)),
            replace(original, method=replace(original.method, output_space="log_odds")),
            replace(original, model_score=original.model_score + 0.01),
            replace(original, base_value=original.base_value + 0.01),
            replace(original, status="unavailable"),
        ]
        for candidate in mutations:
            with self.assertRaises(ExplanationVerificationError):
                self.verify(candidate)

    def test_independent_verifier_rejects_numeric_grouping_and_display_tampering(self):
        original = self.results[0]
        feature = original.features[0]
        mutations = [
            replace(original, encoded_contributions=original.encoded_contributions[:-1]),
            replace(
                original, encoded_contributions=(float("nan"), *original.encoded_contributions[1:])
            ),
            replace(original, features=original.features[:-1]),
            replace(original, features=(replace(feature, name="SAR"), *original.features[1:])),
            replace(
                original,
                features=(replace(feature, missing=not feature.missing), *original.features[1:]),
            ),
            replace(
                original,
                features=(
                    replace(feature, contribution=feature.contribution + 0.01),
                    *original.features[1:],
                ),
            ),
            replace(original, ranking=tuple(reversed(original.ranking))),
            replace(original, top_features=("SAR",)),
            replace(
                original, other_features_contribution=original.other_features_contribution + 0.01
            ),
            replace(original, reconstruction_residual=0.01),
        ]
        for candidate in mutations:
            with self.assertRaises(ExplanationVerificationError):
                self.verify(candidate)

    def test_stale_input_and_wrong_scoring_identity_are_rejected(self):
        original = self.records[0]
        changed = ScoringRecord(original.record_id, {**original.features, "income": 1234567})
        with self.assertRaises(ExplanationVerificationError):
            self.verify(self.results[0], record=changed)
        with self.assertRaises(ExplanationVerificationError):
            self.verify(
                self.results[0], scoring_result=replace(self.scores[0], positive_class_label=True)
            )

    def test_independent_verifier_rejects_extra_target_even_with_matching_hash(self):
        record = ScoringRecord(self.records[0].record_id, {**self.records[0].features, "SAR": 1})
        candidate = replace(self.results[0], input_sha256=input_digest(record))
        with self.assertRaises(ExplanationVerificationError):
            self.verify(candidate, record=record)

    def test_missing_encoded_group_mapping_is_rejected(self):
        with self.assertRaisesRegex(ExplanationVerificationError, "encoded_mapping_invalid"):
            verify_explanation(
                self.results[0],
                self.records[0],
                self.scores[0],
                self.service._loaded,
                tuple(reversed(self.service.encoded_to_original)),
            )

    def test_no_model_fit_or_input_mutation(self):
        from copy import deepcopy

        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier

        record = self.records[0]
        before = deepcopy(dict(record.features))
        with (
            patch.object(
                RandomForestClassifier, "fit", side_effect=AssertionError("RF fit forbidden")
            ),
            patch.object(ColumnTransformer, "fit", side_effect=AssertionError("fit forbidden")),
        ):
            result = self.service.explain_one(record.record_id, record.features)
        self.assertEqual(result.status, "verified")
        self.assertEqual(dict(record.features), before)
        self.assertEqual(self.service._loaded.pipeline.named_steps["fit_scope"].fit_count_, 1)

    def test_concurrent_calls_are_stable(self):
        from concurrent.futures import ThreadPoolExecutor

        record = self.records[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.service.explain_one, record.record_id, record.features)
                for _ in range(2)
            ]
            results = [f.result(timeout=30) for f in futures]
        self.assertEqual(results[0], results[1])

    def test_mathematical_two_feature_path_game_including_native_nan(self):
        import numpy as np
        import shap
        from sklearn.tree import DecisionTreeClassifier

        # One synthetic test-only tree fit; neither project RF nor any project data is fitted.
        matrix = np.array(
            [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0], [np.nan, 0.0], [np.nan, 1.0]]
        )
        tree = DecisionTreeClassifier(max_depth=2, random_state=7).fit(matrix, [0, 0, 0, 1, 0, 1])
        fitted = tree.tree_

        def expectation(row, known, node=0):
            left, right = fitted.children_left[node], fitted.children_right[node]
            if left == right:
                return float(fitted.value[node, 0, 1]) / math.fsum(fitted.value[node, 0])
            feature = fitted.feature[node]
            if feature in known:
                child = (
                    (left if fitted.missing_go_to_left[node] else right)
                    if np.isnan(row[feature])
                    else (left if row[feature] <= fitted.threshold[node] else right)
                )
                return expectation(row, known, child)
            return math.fsum(
                fitted.weighted_n_node_samples[ch]
                / fitted.weighted_n_node_samples[node]
                * expectation(row, known, ch)
                for ch in (left, right)
            )

        expected = []
        for row in matrix:
            base = expectation(row, set())
            expected.append(
                [
                    0.5 * (expectation(row, {j}) - base)
                    + 0.5 * (expectation(row, {0, 1}) - expectation(row, {1 - j}))
                    for j in range(2)
                ]
            )
        explainer = shap.TreeExplainer(
            tree, feature_perturbation="tree_path_dependent", model_output="raw"
        )
        actual = explainer.shap_values(matrix, approximate=False, check_additivity=True)[:, :, 1]
        self.assertLessEqual(float(np.max(np.abs(actual - np.array(expected)))), 1e-12)


@unittest.skipUnless(
    HAS_SHAP_RUNTIME and explanation_reference.REFERENCE_ROOT.is_dir(),
    "Approved original explanation references and Linux runtime required",
)
class ActualSavedExplanationTests(unittest.TestCase):
    def test_original_verified_outputs_match_actual_reference_fixture(self):
        evaluation = load_evaluation()
        ids = frozenset(r.record_id for r in evaluation.records)
        service = explainability.ExplanationService(lambda ident: ident in ids)
        records = list(evaluation.records[:2])
        for predicate in [
            lambda r: r.features["income"] is None,
            lambda r: r.features["income"] == 0,
        ]:
            record = next(r for r in evaluation.records if predicate(r))
            if record not in records:
                records.append(record)
        metadata, lines = load_original_reference(
            ids, service._loaded.fields, service.encoded_to_original
        )
        raw_rows = _verified_csv(DEFAULT_ROOT, FEATURES_PATH)
        raw = {
            r["technical_row_id"]: {name: r[name] for name in service._loaded.fields}
            for r in raw_rows
            if r["technical_row_id"] in ids
        }
        results = service.explain_batch(records)
        for result, record in zip(results, records):
            differences = compare_original(
                result,
                record,
                explanation_reference.strict_json(lines[record.record_id]),
                raw[record.record_id],
                evaluation.reference_scores[record.record_id],
                metadata,
            )
            self.assertTrue(all(delta <= 1e-12 for delta in differences))


if __name__ == "__main__":
    unittest.main()
