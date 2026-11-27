"""Synthetic boundary checks plus real RF scoring and pinned evaluation acceptance."""

import io
import sys
import tempfile
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from test_loader import HAS_REAL_RUNTIME, synthetic  # noqa: E402

from app.schemas.alerts import AlertFeatures  # noqa: E402
from trueflag_ml import regression, scoring  # noqa: E402
from trueflag_ml.loader import DEFAULT_ROOT, ModelLoadError  # noqa: E402
from trueflag_ml.regression import RegressionError  # noqa: E402
from trueflag_ml.scoring import RFScoringService, ScoreResult, ScoringInputError, ScoringRecord  # noqa: E402
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION  # noqa: E402


class ScoringBoundaryTests(unittest.TestCase):
    def test_empty_batch_is_rejected(self):
        with self.assertRaisesRegex(ScoringInputError, "batch_invalid"):
            scoring._validate_batch([])

    def test_oversized_batch_is_rejected(self):
        records = [ScoringRecord(f"r{i}", {}) for i in range(scoring.MAX_BATCH_SIZE + 1)]
        with self.assertRaisesRegex(ScoringInputError, "batch_invalid"):
            scoring._validate_batch(records)

    def test_non_sequence_envelopes_are_rejected(self):
        for value in [None, "records", b"records", {}, iter([]), 123]:
            with self.subTest(type=type(value).__name__):
                with self.assertRaisesRegex(ScoringInputError, "batch_invalid"):
                    scoring._validate_batch(value)

    def test_non_record_items_are_rejected(self):
        with self.assertRaisesRegex(ScoringInputError, "batch_invalid"):
            scoring._validate_batch([{"record_id": "r1", "features": {}}])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ScoringInputError, "duplicate_record_id"):
            scoring._validate_batch([ScoringRecord("r1", {}), ScoringRecord("r1", {})])

    def test_malformed_record_ids_are_rejected(self):
        for ident in [None, 1, True, "", " ", "r\n", "../private", "x" * 129]:
            with self.subTest(type=type(ident).__name__):
                with self.assertRaisesRegex(ScoringInputError, "record_id_invalid"):
                    scoring._validate_batch([ScoringRecord(ident, {})])

    def test_maximum_batch_envelope_is_accepted(self):
        scoring._validate_batch(
            tuple(ScoringRecord(f"r{i}", {}) for i in range(scoring.MAX_BATCH_SIZE))
        )

    def test_missing_artifact_prevents_service_initialization(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ModelLoadError, "artifact_missing"):
                RFScoringService(Path(name))

    def test_unapproved_model_prevents_service_initialization(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / MODEL_PATH
            path.parent.mkdir()
            path.write_bytes(b"unapproved model")
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                RFScoringService(Path(name))


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.fields = tuple(AlertFeatures.model_fields)
        self.references = [
            {
                "technical_row_id": "r2",
                "SAR": "1",
                "model": "RF",
                "execution_status": "processed",
                "score": "0.8",
            },
            {
                "technical_row_id": "r1",
                "SAR": "0",
                "model": "RF",
                "execution_status": "processed",
                "score": "0.2",
            },
        ]
        self.rows = [
            {
                **synthetic(),
                "technical_row_id": "r1",
                "SAR": "0",
                "csrNotes": "must-not-enter-features",
            },
            {**synthetic(), "technical_row_id": "r2", "SAR": "1"},
        ]

    def align(self):
        return regression._aligned_rows(self.references, self.rows, self.fields, 2)

    def test_alignment_uses_ids_and_reference_order(self):
        scores, features = self.align()
        self.assertEqual(tuple(scores), ("r2", "r1"))
        self.assertEqual(tuple(features[0]), self.fields)
        self.assertNotIn("SAR", features[0])
        self.assertNotIn("csrNotes", features[1])
        self.assertNotIn("technical_row_id", features[0])

    def test_duplicate_reference_id_is_rejected(self):
        self.references[1]["technical_row_id"] = "r2"
        with self.assertRaisesRegex(RegressionError, "duplicate_reference_id"):
            self.align()

    def test_duplicate_feature_id_is_rejected(self):
        self.rows.append(self.rows[0].copy())
        with self.assertRaisesRegex(RegressionError, "duplicate_feature_id"):
            self.align()

    def test_duplicate_unselected_source_id_is_also_rejected(self):
        self.rows.extend([{"technical_row_id": "training"}, {"technical_row_id": "training"}])
        with self.assertRaisesRegex(RegressionError, "duplicate_feature_id"):
            self.align()

    def test_missing_evaluation_features_are_rejected(self):
        self.rows.pop()
        with self.assertRaisesRegex(RegressionError, "evaluation_ids_mismatch"):
            self.align()

    def test_mismatched_reference_ids_are_rejected(self):
        self.references[0]["technical_row_id"] = "unmatched"
        with self.assertRaisesRegex(RegressionError, "evaluation_ids_mismatch"):
            self.align()

    def test_reference_count_is_enforced(self):
        self.references.pop()
        with self.assertRaisesRegex(RegressionError, "reference_count_invalid"):
            self.align()

    def test_reference_and_source_label_mismatch_is_rejected(self):
        self.rows[0]["SAR"] = "1"
        with self.assertRaisesRegex(RegressionError, "reference_label_mismatch"):
            self.align()

    def test_missing_predictor_is_rejected(self):
        del self.rows[0]["income"]
        with self.assertRaisesRegex(RegressionError, "feature_schema_invalid"):
            self.align()

    def test_invalid_reference_probability_is_rejected(self):
        for value in ["nan", "inf", "-0.1", "1.1"]:
            self.references[0]["score"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(RegressionError, "reference_score_invalid"):
                    self.align()

    def test_failed_reference_or_wrong_model_is_rejected(self):
        self.references[0]["execution_status"] = "Not processed"
        with self.assertRaisesRegex(RegressionError, "reference_status_invalid"):
            self.align()
        self.references[0].update(execution_status="processed", model="other")
        with self.assertRaisesRegex(RegressionError, "reference_status_invalid"):
            self.align()


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.references = {"r1": 0.2, "r2": 0.8}
        self.results = [
            ScoreResult(ident, score, MODEL_VERSION, APPROVED_SHA256[MODEL_PATH], "processed")
            for ident, score in self.references.items()
        ]

    def test_comparison_matches_by_id_not_output_order(self):
        report = regression.compare_results(self.references, reversed(self.results))
        self.assertTrue(report.passed)
        self.assertEqual(report.matched_records, 2)
        self.assertEqual(report.maximum_absolute_error, 0)

    def test_duplicate_result_id_is_rejected(self):
        with self.assertRaisesRegex(RegressionError, "duplicate_result_id"):
            regression.compare_results(self.references, self.results + self.results[:1])

    def test_missing_result_id_is_rejected(self):
        with self.assertRaisesRegex(RegressionError, "result_ids_mismatch"):
            regression.compare_results(self.references, self.results[:1])

    def test_unexpected_result_id_is_rejected(self):
        self.results[1] = replace(self.results[1], record_id="unexpected")
        with self.assertRaisesRegex(RegressionError, "result_ids_mismatch"):
            regression.compare_results(self.references, self.results)

    def test_wrong_model_or_class_identity_is_rejected(self):
        for update in [
            {"model_version": "other"},
            {"model_sha256": "other"},
            {"positive_class_label": 0},
        ]:
            changed = [replace(self.results[0], **update), self.results[1]]
            with self.subTest(fields=tuple(update)):
                with self.assertRaisesRegex(RegressionError, "result_model_mismatch"):
                    regression.compare_results(self.references, changed)

    def test_failed_scoring_never_counts_as_matching_prediction(self):
        self.results[0] = replace(
            self.results[0], score=None, processing_status="failed", reason="inference_failed"
        )
        report = regression.compare_results(self.references, self.results)
        self.assertFalse(report.passed)
        self.assertEqual(report.processing_failures, 1)
        self.assertEqual(report.scored_records, 1)
        self.assertEqual(report.mismatches, 1)

    def test_numeric_mismatch_is_reported_without_adjustment(self):
        self.results[0] = replace(self.results[0], score=0.3)
        report = regression.compare_results(self.references, self.results)
        self.assertEqual(report.mismatches, 1)
        self.assertAlmostEqual(report.maximum_absolute_error, 0.1)
        self.assertEqual(report.absolute_tolerance, 1e-12)
        self.assertEqual(report.relative_tolerance, 0)

    def test_absolute_tolerance_is_applied(self):
        self.results[0] = replace(self.results[0], score=0.2 + 1e-13)
        self.assertTrue(regression.compare_results(self.references, self.results).passed)

    def test_nonfinite_reference_cannot_silently_pass(self):
        for value in [float("nan"), float("inf"), True, "0.2", 10**10000]:
            self.references["r1"] = value
            with self.subTest(type=type(value).__name__):
                with self.assertRaisesRegex(RegressionError, "reference_score_invalid"):
                    regression.compare_results(self.references, self.results)

    def test_nonfinite_result_is_counted_as_processing_failure(self):
        self.results[0] = replace(self.results[0], score=float("nan"))
        self.assertEqual(
            regression.compare_results(self.references, self.results).processing_failures, 1
        )

    def test_empty_reference_cannot_pass(self):
        with self.assertRaisesRegex(RegressionError, "reference_count_invalid"):
            regression.compare_results({}, [])


@unittest.skipUnless(
    HAS_REAL_RUNTIME, "Private model/scientific runtime absent; run .venv-ml acceptance"
)
class RealScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = RFScoringService()
        cls.evaluation = regression.load_evaluation()

    def test_all_4000_reference_predictions_match(self):
        report = regression.score_evaluation(self.service, self.evaluation)
        self.assertEqual(report.matched_records, 4000)
        self.assertEqual(report.scored_records, 4000)
        self.assertEqual(report.processing_failures, 0)
        self.assertEqual(report.mismatches, 0)
        self.assertLessEqual(report.maximum_absolute_error, 1e-12)

    def test_changed_batch_boundaries_preserve_all_reference_scores(self):
        report = regression.score_evaluation(self.service, self.evaluation, batch_size=137)
        self.assertTrue(report.passed)
        self.assertEqual(report.matched_records, 4000)

    def test_single_predictions_match_batch_and_repeat_deterministically(self):
        records = self.evaluation.records[:12]
        expected = self.service.score_batch(records)
        self.assertEqual(expected, self.service.score_batch(records))
        self.assertEqual(
            expected, tuple(self.service.score_one(r.record_id, r.features) for r in records)
        )
        reordered = self.service.score_batch(tuple(reversed(records)))
        self.assertEqual(expected, tuple(reversed(reordered)))

    def test_positive_class_matches_actual_full_pipeline_mapping(self):
        record = self.evaluation.records[0]
        loaded = self.service._loaded
        classes = list(loaded.pipeline.classes_)
        self.assertEqual(classes, [0, 1])
        expected = loaded.pipeline.predict_proba(loaded.feature_frame(record.features))[
            0, classes.index(1)
        ]
        result = self.service.score_one(record.record_id, record.features)
        self.assertEqual(result.score, float(expected))
        self.assertEqual(result.positive_class_label, 1)

    def test_invalid_row_is_rejected_without_poisoning_valid_rows(self):
        batch = [
            ScoringRecord("missing", synthetic()),
            ScoringRecord("invalid", {**synthetic(), "SAR": 1}),
            ScoringRecord("zero", synthetic(0)),
        ]
        results = self.service.score_batch(batch)
        self.assertEqual(
            [r.processing_status for r in results], ["processed", "failed", "processed"]
        )
        self.assertIsNone(results[1].score)
        self.assertEqual(results[1].reason, "invalid_features")

    def test_missing_and_zero_income_reach_original_preprocessing_unchanged(self):
        import numpy as np

        loaded = self.service._loaded
        original = loaded.pipeline.predict_proba
        observed = []

        def actual_prediction(frame):
            observed.append(frame.copy())
            return original(frame)

        with patch.object(loaded.pipeline, "predict_proba", side_effect=actual_prediction):
            results = self.service.score_batch(
                [ScoringRecord("missing", synthetic()), ScoringRecord("zero", synthetic(0))]
            )
        self.assertTrue(all(r.processing_status == "processed" for r in results))
        self.assertEqual(tuple(observed[0].columns), loaded.fields)
        self.assertTrue(np.isnan(observed[0].loc[0, "income"]))
        self.assertEqual(observed[0].loc[1, "income"], 0)
        pre = loaded.pipeline.named_steps["preprocessor"]
        index = pre.output_indices_["numeric"].start + pre.transformers_[1][2].index("income")
        transformed = pre.transform(observed[0])
        self.assertTrue(np.isnan(transformed[0, index]))
        self.assertEqual(transformed[1, index], 0)

    def test_invalid_features_produce_sanitized_failure(self):
        for features in [
            None,
            {},
            {**synthetic(), "income": "0"},
            {**synthetic(), "income": float("nan")},
            {**synthetic(), "kycRiskScore": 7},
            {**synthetic(), "private-customer-marker": "secret"},
        ]:
            with self.subTest(type=type(features).__name__):
                result = self.service.score_one("invalid", features)
                self.assertEqual(result.reason, "invalid_features")
                self.assertEqual(result.processing_status, "failed")
                self.assertIsNone(result.score)
                self.assertNotIn("private-customer-marker", repr(result))

    def test_duplicate_requests_are_rejected_before_prediction(self):
        pipeline = self.service._loaded.pipeline
        with patch.object(
            pipeline, "predict_proba", side_effect=AssertionError("must not score")
        ) as blocked:
            with self.assertRaisesRegex(ScoringInputError, "duplicate_record_id"):
                self.service.score_batch(
                    [
                        ScoringRecord("duplicate", synthetic()),
                        ScoringRecord("duplicate", synthetic(0)),
                    ]
                )
            blocked.assert_not_called()

    def test_inference_exception_fails_without_logging_private_values(self):
        output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            patch.object(
                self.service._loaded.pipeline,
                "predict_proba",
                side_effect=RuntimeError("private-feature-marker"),
            ),
        ):
            result = self.service.score_one("failure", synthetic())
        self.assertEqual(result.reason, "inference_failed")
        self.assertIsNone(result.score)
        self.assertNotIn("private-feature-marker", output.getvalue() + repr(result))

    def test_inference_warning_fails_without_rendering_private_values(self):
        def warning(frame):
            warnings.warn("private-feature-marker", UserWarning)

        output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            patch.object(self.service._loaded.pipeline, "predict_proba", side_effect=warning),
        ):
            result = self.service.score_one("warning", synthetic())
        self.assertEqual(result.reason, "inference_failed")
        self.assertNotIn("private-feature-marker", output.getvalue() + repr(result))

    def test_malformed_nonfinite_or_out_of_range_outputs_fail(self):
        import numpy as np

        invalid = [
            np.zeros((1, 1)),
            [[0.2, 0.8]],
            np.array([[float("nan"), 0.8]]),
            np.array([[0.2, float("inf")]]),
            np.array([[-0.1, 1.1]]),
            np.array([[0.2, 0.2]]),
            np.array([["0.2", "0.8"]]),
        ]
        for values in invalid:
            with self.subTest(type=type(values).__name__):
                with patch.object(
                    self.service._loaded.pipeline, "predict_proba", return_value=values
                ):
                    result = self.service.score_one("bad-output", synthetic())
                self.assertEqual(result.reason, "invalid_model_output")
                self.assertIsNone(result.score)

    def test_changed_classes_fail_before_prediction(self):
        import numpy as np

        forest = self.service._loaded.pipeline.named_steps["estimator"]
        with (
            patch.object(forest, "classes_", np.array([1, 0])),
            patch.object(
                self.service._loaded.pipeline,
                "predict_proba",
                side_effect=AssertionError("must not score"),
            ) as blocked,
        ):
            result = self.service.score_one("wrong-class", synthetic())
            blocked.assert_not_called()
        self.assertEqual(result.reason, "model_state_invalid")

    def test_concurrent_calls_are_deterministic_and_restore_warning_filters(self):
        records = self.evaluation.records[:16]
        expected = self.service.score_batch(records)
        filters = list(warnings.filters)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.service.score_batch, records) for _ in range(2)]
            self.assertTrue(all(f.result(timeout=20) == expected for f in futures))
        self.assertEqual(warnings.filters, filters)

    def test_no_fit_is_called_and_input_is_not_mutated(self):
        from copy import deepcopy

        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier

        features = synthetic(0)
        before = deepcopy(features)
        with (
            patch.object(
                RandomForestClassifier, "fit", side_effect=AssertionError("fit forbidden")
            ),
            patch.object(ColumnTransformer, "fit", side_effect=AssertionError("fit forbidden")),
        ):
            result = self.service.score_one("read-only", features)
        self.assertEqual(result.processing_status, "processed")
        self.assertEqual(features, before)
        self.assertEqual(self.service._loaded.pipeline.named_steps["fit_scope"].fit_count_, 1)

    def test_changed_reference_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / regression.REFERENCE_PATH
            path.parent.mkdir(parents=True)
            path.write_bytes((DEFAULT_ROOT / regression.REFERENCE_PATH).read_bytes() + b"\n")
            with self.assertRaisesRegex(RegressionError, "reference_integrity_failed"):
                regression.load_evaluation(root)

    def test_missing_reference_fails_safely(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RegressionError, "reference_missing"):
                regression.load_evaluation(Path(name))


if __name__ == "__main__":
    unittest.main()
