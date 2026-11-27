"""Pure validation checks, real frozen-policy acceptance and actual 12000-trace regression."""

import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from test_loader import HAS_REAL_RUNTIME  # noqa: E402

from app.schemas.alerts import AlertFeatures  # noqa: E402
from trueflag_ml import policy, policy_regression  # noqa: E402
from trueflag_ml.loader import DEFAULT_ROOT  # noqa: E402
from trueflag_ml.policy import PolicyInputError, RiskPolicyEngine  # noqa: E402
from trueflag_ml.regression import RegressionError  # noqa: E402
from trueflag_ml.scoring import ScoreResult  # noqa: E402
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION  # noqa: E402

HAS_POLICY = (DEFAULT_ROOT / policy.POLICY_PATH).is_file()


def score(value=0.1, **changes):
    return replace(
        ScoreResult("synthetic-1", value, MODEL_VERSION, APPROVED_SHA256[MODEL_PATH], "processed"),
        **changes,
    )


def minimal_settings():
    # Public contract fixture for parser/comparison units, never accepted as a trusted file.
    return {
        "model": "RF",
        "model_version": MODEL_VERSION,
        "pipeline_sha256": APPROVED_SHA256[MODEL_PATH],
        "scorer_predictors": list(AlertFeatures.model_fields),
        "thresholds": {
            "Efficiency": 0.19088491043724937,
            "Balanced": 0.16040515630453706,
            "Coverage": 0.16040515630453706,
        },
        "priority_mapping": {"Standard": [0, 1, 2], "High": [3, 4, 5, 6]},
    }


class PolicyValidationTests(unittest.TestCase):
    def test_valid_score_bounds_and_native_numeric_types(self):
        for value in [0, 1, 0.0, 1.0, 0.5]:
            self.assertEqual(policy.validate_score(value), float(value))

    def test_booleans_are_not_scores(self):
        for value in [True, False]:
            with self.assertRaisesRegex(PolicyInputError, "invalid_score"):
                policy.validate_score(value)

    def test_nonfinite_out_of_range_and_wrong_score_types_fail(self):
        for value in [
            None,
            "0.5",
            [],
            {},
            float("nan"),
            float("inf"),
            -float("inf"),
            -0.1,
            1.1,
            10**10000,
        ]:
            with self.subTest(type=type(value).__name__):
                with self.assertRaisesRegex(PolicyInputError, "invalid_score"):
                    policy.validate_score(value)

    def test_all_supported_kyc_values_derive_project_priority(self):
        for value in range(7):
            expected = (value, "High" if value >= 3 else "Standard")
            self.assertEqual(policy.validate_priority(value), expected)
            self.assertEqual(policy.validate_priority(float(value)), expected)

    def test_invalid_kyc_is_never_defaulted_to_standard(self):
        for value in [None, True, False, "3", -1, 7, 3.5, float("nan"), float("inf"), 10**10000]:
            with self.subTest(type=type(value).__name__):
                with self.assertRaisesRegex(PolicyInputError, "invalid_kyc"):
                    policy.validate_priority(value)

    def test_declared_priority_must_match_kyc(self):
        for value, declared in [(0, "High"), (6, "Standard")]:
            with self.assertRaisesRegex(PolicyInputError, "priority_mismatch"):
                policy.validate_priority(value, declared)

    def test_priority_labels_are_strict(self):
        for declared in [True, False, "high", " High", "unknown", 3, []]:
            with self.subTest(type=type(declared).__name__):
                with self.assertRaisesRegex(PolicyInputError, "invalid_priority"):
                    policy.validate_priority(3, declared)

    def test_matching_declared_priority_is_accepted(self):
        self.assertEqual(policy.validate_priority(3, "High"), (3, "High"))
        self.assertEqual(policy.validate_priority(2, "Standard"), (2, "Standard"))

    def test_malformed_settings_fail_without_content_in_error(self):
        for content in [b"[]", b"null", b"{}", b"private-marker"]:
            with self.assertRaisesRegex(policy.PolicyLoadError, "policy_schema_invalid"):
                policy._parse_settings(content)

    def test_schema_rejects_boolean_or_nonfinite_thresholds(self):
        for value in [True, float("nan"), float("inf"), "0.16", 0.0, 1.0]:
            settings = minimal_settings()
            settings["thresholds"]["Balanced"] = value
            with self.assertRaisesRegex(policy.PolicyLoadError, "policy_schema_invalid"):
                policy._parse_settings(json.dumps(settings))

    def test_schema_requires_frozen_priority_and_model_identity(self):
        for field, value in [
            ("model", "other"),
            ("model_version", "other"),
            ("pipeline_sha256", "other"),
            ("scorer_predictors", ["SAR"]),
        ]:
            settings = {**minimal_settings(), field: value}
            with self.assertRaisesRegex(policy.PolicyLoadError, "policy_schema_invalid"):
                policy._parse_settings(json.dumps(settings))
        settings = minimal_settings()
        settings["priority_mapping"]["Standard"] = [0, 1, True]
        with self.assertRaisesRegex(policy.PolicyLoadError, "policy_schema_invalid"):
            policy._parse_settings(json.dumps(settings))

    def test_schema_requires_equal_balanced_coverage_thresholds(self):
        settings = minimal_settings()
        settings["thresholds"]["Coverage"] = 0.15
        with self.assertRaisesRegex(policy.PolicyLoadError, "policy_schema_invalid"):
            policy._parse_settings(json.dumps(settings))

    def test_missing_policy_is_unready_and_requires_manual_review(self):
        with tempfile.TemporaryDirectory() as name:
            engine = RiskPolicyEngine(Path(name))
            result = engine.evaluate(score(), "Coverage", kyc_risk_score=6)
        self.assertFalse(engine.ready)
        self.assertEqual(engine.load_failure, "policy_artifact_missing")
        self.assertEqual(result.recommended_route, "manual_review")
        self.assertEqual(result.processing_status, "failed")
        self.assertIsNone(result.policy_version)
        self.assertIsNone(result.model_score)
        self.assertFalse(result.coverage_protection)
        self.assertTrue(result.human_decision_required)

    def test_unapproved_policy_never_uses_default_thresholds(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            target = root / policy.POLICY_PATH
            target.parent.mkdir()
            target.write_text(json.dumps(minimal_settings()))
            engine = RiskPolicyEngine(root)
            result = engine.evaluate(score(1), "Efficiency", kyc_risk_score=0)
        self.assertFalse(engine.ready)
        self.assertEqual(engine.load_failure, "policy_integrity_failed")
        self.assertEqual(result.recommended_route, "manual_review")
        self.assertIsNone(result.threshold)

    def test_unexpected_loader_failure_is_sanitized(self):
        output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            patch.object(
                policy, "load_approved_policy", side_effect=RuntimeError("private-marker")
            ),
        ):
            engine = RiskPolicyEngine()
            result = engine.evaluate(score(), "Balanced", kyc_risk_score=0)
        self.assertEqual(engine.load_failure, "policy_load_failed")
        self.assertEqual(result.recommended_route, "manual_review")
        self.assertNotIn("private-marker", output.getvalue() + repr(result))


@unittest.skipUnless(HAS_POLICY, "Private frozen policy is absent")
class ActualPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RiskPolicyEngine()
        if not cls.engine.ready:
            raise AssertionError("Actual frozen policy verification failed")

    def manual(self, result):
        self.assertEqual(result.recommended_route, "manual_review")
        self.assertEqual(result.processing_status, "failed")
        self.assertIsNone(result.model_score)
        self.assertFalse(result.score_based_retention)
        self.assertFalse(result.coverage_protection)
        self.assertFalse(result.coverage_changed_route)
        self.assertIsNone(result.override_reason)
        self.assertTrue(result.human_decision_required)

    def test_real_settings_preserve_exact_values_and_identity(self):
        settings = self.engine.settings
        self.assertEqual(settings.thresholds, minimal_settings()["thresholds"])
        self.assertEqual(settings.version, f"{MODEL_VERSION}:{policy.POLICY_SHA256}")
        with self.assertRaises(TypeError):
            settings.thresholds["Coverage"] = 0.0

    def test_every_threshold_uses_inclusive_unrounded_boundary(self):
        for mode in policy.MODES:
            threshold = self.engine.settings.thresholds[mode]
            for value, route in [
                (math.nextafter(threshold, 0.0), "review_reduction_candidate"),
                (threshold, "retain_human_review"),
                (math.nextafter(threshold, 1.0), "retain_human_review"),
            ]:
                with self.subTest(mode=mode, boundary=value == threshold):
                    result = self.engine.evaluate(score(value), mode, kyc_risk_score=2)
                    self.assertEqual(result.recommended_route, route)
                    self.assertEqual(result.model_score, value)
                    self.assertEqual(result.threshold, threshold)

    def test_coverage_retains_every_successful_high_priority_kyc(self):
        for kyc in [3, 4, 5, 6, 3.0]:
            result = self.engine.evaluate(score(0), "Coverage", kyc_risk_score=kyc)
            self.assertEqual(result.recommended_route, "retain_human_review")
            self.assertEqual(result.override_reason, "coverage_high_priority_protection")
            self.assertTrue(result.coverage_changed_route)
            self.assertFalse(result.score_based_retention)

    def test_efficiency_and_balanced_have_no_high_priority_override(self):
        for mode in ["Efficiency", "Balanced"]:
            result = self.engine.evaluate(score(0), mode, kyc_risk_score=6)
            self.assertEqual(result.recommended_route, "review_reduction_candidate")
            self.assertIsNone(result.override_reason)
            self.assertFalse(result.coverage_protection)

    def test_standard_priority_has_no_coverage_override(self):
        for kyc in [0, 1, 2]:
            result = self.engine.evaluate(score(0), "Coverage", kyc_risk_score=kyc)
            self.assertEqual(result.recommended_route, "review_reduction_candidate")
            self.assertFalse(result.coverage_changed_route)

    def test_above_threshold_high_case_records_protection_without_false_override(self):
        result = self.engine.evaluate(score(1), "Coverage", kyc_risk_score=3)
        self.assertEqual(result.recommended_route, "retain_human_review")
        self.assertTrue(result.coverage_protection)
        self.assertFalse(result.coverage_changed_route)
        self.assertIsNone(result.override_reason)
        self.assertEqual(
            result.routing_reason, "score_at_or_above_threshold_and_coverage_high_priority"
        )

    def test_failed_high_priority_score_never_gets_successful_retention_credit(self):
        for assessment in [
            score(None, processing_status="failed", reason="inference_failed"),
            score(0.1, processing_status="failed"),
            score(0.1, reason="private-error"),
        ]:
            for mode in policy.MODES:
                result = self.engine.evaluate(assessment, mode, kyc_risk_score=6)
                self.manual(result)
                self.assertEqual(result.routing_reason, "scoring_failed_manual_review_required")

    def test_invalid_scores_are_manual_review_even_when_high_priority(self):
        for value in [True, False, None, "0.2", -1, 2, float("nan"), float("inf"), -float("inf")]:
            result = self.engine.evaluate(score(value), "Coverage", kyc_risk_score=6)
            self.manual(result)
            self.assertEqual(result.routing_reason, "invalid_score")

    def test_bad_kyc_and_priority_cannot_force_retention(self):
        for kyc in [None, True, 7, -1, 3.5, "3", float("nan")]:
            result = self.engine.evaluate(score(0), "Coverage", kyc_risk_score=kyc)
            self.manual(result)
        self.manual(
            self.engine.evaluate(score(0), "Coverage", kyc_risk_score=0, priority_group="High")
        )
        self.manual(
            self.engine.evaluate(score(0), "Coverage", kyc_risk_score=3, priority_group=True)
        )

    def test_unknown_policies_are_not_defaulted_or_echoed(self):
        for mode in [None, True, 1, [], "coverage", "private-marker"]:
            result = self.engine.evaluate(score(), mode, kyc_risk_score=0)
            self.manual(result)
            self.assertIsNone(result.selected_policy)
            self.assertIsNone(result.threshold)
            self.assertNotIn("private-marker", repr(result))

    def test_invalid_record_references_are_not_echoed(self):
        for ident in [None, True, "../private-marker", "invalid\n"]:
            result = self.engine.evaluate(score(record_id=ident), "Balanced", kyc_risk_score=0)
            self.manual(result)
            self.assertIsNone(result.record_id)

    def test_wrong_model_or_class_identity_requires_manual_review(self):
        for changes in [
            {"model_version": "other"},
            {"model_sha256": "other"},
            {"positive_class_label": True},
            {"positive_class_label": 0},
        ]:
            self.manual(self.engine.evaluate(score(**changes), "Coverage", kyc_risk_score=6))

    def test_missing_and_malformed_score_results_fail_safely(self):
        for assessment in [None, {}, True, "private-marker"]:
            result = self.engine.evaluate(assessment, "Balanced", kyc_risk_score=0)
            self.manual(result)
            self.assertNotIn("private-marker", repr(result))

    def test_evaluation_exception_is_sanitized_to_manual_review(self):
        output = io.StringIO()
        with (
            redirect_stdout(output),
            redirect_stderr(output),
            patch.object(self.engine, "_recommend", side_effect=RuntimeError("private-marker")),
        ):
            result = self.engine.evaluate(score(), "Efficiency", kyc_risk_score=0)
        self.manual(result)
        self.assertEqual(result.routing_reason, "policy_evaluation_failed")
        self.assertNotIn("private-marker", output.getvalue() + repr(result))

    def test_successful_recommendations_always_require_human_decision(self):
        for mode in policy.MODES:
            for value in [0, 1]:
                result = self.engine.evaluate(score(value), mode, kyc_risk_score=0)
                self.assertTrue(result.human_decision_required)
                self.assertNotEqual(result.recommended_route, "Dismiss")

    def test_policy_execution_never_imports_or_invokes_scientific_runtime(self):
        code = "import sys; sys.path.insert(0,'backend'); from trueflag_ml.policy import RiskPolicyEngine; from trueflag_ml.scoring import ScoreResult; from trueflag_ml.trust import MODEL_VERSION,APPROVED_SHA256,MODEL_PATH; e=RiskPolicyEngine(); r=e.evaluate(ScoreResult('synthetic',0.5,MODEL_VERSION,APPROVED_SHA256[MODEL_PATH],'processed'),'Balanced',kyc_risk_score=0); assert r.processing_status=='processed'; assert not {'numpy','sklearn','joblib'} & sys.modules.keys()"
        result = subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=BACKEND.parent, capture_output=True
        )
        self.assertEqual(result.returncode, 0, "Policy/scientific isolation failed")

    def test_repeated_and_concurrent_evaluation_is_deterministic(self):
        from concurrent.futures import ThreadPoolExecutor

        expected = self.engine.evaluate(score(), "Coverage", kyc_risk_score=6)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(
                    lambda _: self.engine.evaluate(score(), "Coverage", kyc_risk_score=6), range(16)
                )
            )
        self.assertTrue(all(result == expected for result in results))

    def test_retained_sets_are_monotonic_across_all_modes_and_kyc_groups(self):
        thresholds = self.engine.settings.thresholds
        values = [0, thresholds["Balanced"], thresholds["Efficiency"], 1]
        for kyc in range(7):
            for value in values:
                retained = [
                    self.engine.evaluate(score(value), mode, kyc_risk_score=kyc).recommended_route
                    == "retain_human_review"
                    for mode in policy.MODES
                ]
                self.assertLessEqual(retained[0], retained[1])
                self.assertLessEqual(retained[1], retained[2])

    def test_changed_artifact_is_rejected_and_original_is_unchanged(self):
        content = (DEFAULT_ROOT / policy.POLICY_PATH).read_bytes()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / policy.POLICY_PATH
            path.parent.mkdir()
            path.write_bytes(content + b"\n")
            engine = RiskPolicyEngine(root)
            self.assertFalse(engine.ready)
            self.manual(engine.evaluate(score(), "Balanced", kyc_risk_score=0))
        self.assertEqual((DEFAULT_ROOT / policy.POLICY_PATH).read_bytes(), content)


class PolicyComparisonTests(unittest.TestCase):
    def setUp(self):
        self.settings = policy._parse_settings(json.dumps(minimal_settings()))
        self.rows, self.results = [], []
        for mode in policy.MODES:
            self.rows.append(
                {
                    "technical_row_id": "synthetic-1",
                    "model_version": MODEL_VERSION,
                    "pipeline_sha256": APPROVED_SHA256[MODEL_PATH],
                    "policy_settings_sha256": policy.POLICY_SHA256,
                    "mode": mode,
                    "score": "0.1",
                    "threshold": str(self.settings.thresholds[mode]),
                    "kycRiskScore": "0",
                    "priority_group": "Standard",
                    "score_based_retention": "False",
                    "coverage_protection": "False",
                    "coverage_changed_route": "False",
                    "execution_status": "processed",
                    "final_route": "Dismiss",
                    "manual_review_required": "False",
                    "routing_reason": "score_below_threshold",
                }
            )
            self.results.append(
                policy.PolicyRecommendation(
                    record_id="synthetic-1",
                    model_score=0.1,
                    selected_policy=mode,
                    policy_version=self.settings.version,
                    policy_sha256=policy.POLICY_SHA256,
                    model_version=MODEL_VERSION,
                    model_sha256=APPROVED_SHA256[MODEL_PATH],
                    threshold=self.settings.thresholds[mode],
                    kyc_risk_score=0,
                    priority_group="Standard",
                    recommended_route="review_reduction_candidate",
                    override_reason=None,
                    processing_status="processed",
                    routing_reason="score_below_threshold",
                )
            )

    def compare(self):
        return policy_regression.compare_policy_results(
            self.rows, self.results, ["synthetic-1"], self.settings
        )

    def test_results_match_by_id_and_policy_independent_of_order(self):
        self.results.reverse()
        report = self.compare()
        self.assertTrue(report.passed)
        self.assertEqual(report.matched_routes, 3)

    def test_duplicate_reference_pairs_are_rejected(self):
        self.rows[1] = self.rows[0].copy()
        with self.assertRaisesRegex(RegressionError, "duplicate_policy_trace"):
            self.compare()

    def test_missing_reference_pairs_are_rejected(self):
        self.rows.pop()
        with self.assertRaisesRegex(RegressionError, "policy_trace_ids_mismatch"):
            self.compare()

    def test_unknown_reference_case_is_rejected(self):
        self.rows[0]["technical_row_id"] = "unexpected"
        with self.assertRaisesRegex(RegressionError, "policy_trace_ids_mismatch"):
            self.compare()

    def test_unknown_reference_policy_is_rejected(self):
        self.rows[0]["mode"] = "other"
        with self.assertRaisesRegex(RegressionError, "policy_trace_mode_invalid"):
            self.compare()

    def test_duplicate_recommendations_are_rejected(self):
        self.results.append(self.results[0])
        with self.assertRaisesRegex(RegressionError, "duplicate_policy_result"):
            self.compare()

    def test_missing_or_foreign_recommendation_is_rejected(self):
        self.results[0] = replace(self.results[0], record_id="foreign")
        with self.assertRaisesRegex(RegressionError, "policy_result_ids_mismatch"):
            self.compare()

    def test_reference_identity_and_priority_are_validated(self):
        self.rows[0]["policy_settings_sha256"] = "other"
        with self.assertRaisesRegex(RegressionError, "policy_trace_identity_invalid"):
            self.compare()
        self.rows[0]["policy_settings_sha256"] = policy.POLICY_SHA256
        self.rows[0]["priority_group"] = "High"
        with self.assertRaisesRegex(RegressionError, "policy_trace_priority_invalid"):
            self.compare()

    def test_reference_nonfinite_score_and_rounded_threshold_are_rejected(self):
        self.rows[0]["score"] = "nan"
        with self.assertRaisesRegex(RegressionError, "policy_trace_score_invalid"):
            self.compare()
        self.rows[0]["score"] = "0.1"
        self.rows[0]["threshold"] = "0.191"
        with self.assertRaisesRegex(RegressionError, "policy_trace_score_invalid"):
            self.compare()

    def test_route_mismatch_reports_retained_and_dismissed_differences(self):
        self.results[0] = replace(self.results[0], recommended_route="retain_human_review")
        report = self.compare()
        self.assertFalse(report.passed)
        self.assertEqual(report.route_mismatches, 1)
        self.assertEqual(report.totals[0].retained_difference, 1)
        self.assertEqual(report.totals[0].dismissed_difference, -1)

    def test_audit_reason_mismatch_is_detected_even_when_route_matches(self):
        self.results[0] = replace(self.results[0], routing_reason="wrong")
        report = self.compare()
        self.assertEqual(report.route_mismatches, 0)
        self.assertEqual(report.trace_mismatches, 1)

    def test_failed_evaluation_gets_no_retention_or_dismissal_credit(self):
        self.results[0] = replace(
            self.results[0],
            recommended_route="manual_review",
            model_score=None,
            processing_status="failed",
        )
        report = self.compare()
        self.assertEqual(report.processing_failures, 1)
        self.assertEqual(report.totals[0].retained, 0)
        self.assertEqual(report.totals[0].review_reduction_candidates, 0)
        self.assertEqual(report.totals[0].dismissed_difference, -1)

    def test_policy_version_or_human_control_mismatch_is_detected(self):
        self.results[0] = replace(
            self.results[0], policy_version="other", human_decision_required=False
        )
        self.assertEqual(self.compare().trace_mismatches, 1)

    def test_missing_trace_artifact_fails_safely(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RegressionError, "policy_trace_missing"):
                policy_regression.load_policy_traces(Path(name))

    def test_out_of_range_result_cannot_pass_within_numeric_tolerance(self):
        self.rows[0]["score"] = "0.0"
        self.results[0] = replace(self.results[0], model_score=-1e-13)
        self.assertEqual(self.compare().trace_mismatches, 1)

    def test_unhashable_expected_record_id_is_rejected_safely(self):
        with self.assertRaisesRegex(RegressionError, "policy_record_ids_invalid"):
            policy_regression.compare_policy_results(self.rows, self.results, [[]], self.settings)

    def test_unapproved_trace_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / policy_regression.TRACE_PATH
            path.parent.mkdir()
            path.write_bytes(b"unapproved traces")
            with self.assertRaisesRegex(RegressionError, "policy_trace_integrity_failed"):
                policy_regression.load_policy_traces(Path(name))


@unittest.skipUnless(
    HAS_REAL_RUNTIME, "Private model/scientific runtime absent; run .venv-ml acceptance"
)
class ActualPolicyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = policy_regression.run_policy_regression()

    def test_all_12000_routes_and_audit_traces_match_actual_rf_scores(self):
        report = self.report.policy_regression
        self.assertTrue(self.report.passed)
        self.assertEqual(report.matched_routes, 12000)
        self.assertEqual(report.route_mismatches, 0)
        self.assertEqual(report.trace_mismatches, 0)
        self.assertEqual(report.processing_failures, 0)

    def test_all_mode_totals_match_and_coverage_has_456_overrides(self):
        totals = self.report.policy_regression.totals
        self.assertEqual(
            [(t.retained, t.review_reduction_candidates) for t in totals],
            [(934, 3066), (1004, 2996), (1460, 2540)],
        )
        self.assertTrue(all(t.retained_difference == t.dismissed_difference == 0 for t in totals))
        self.assertEqual([t.high_priority_overrides for t in totals], [0, 0, 456])

    def test_rf_regression_stays_exact_without_model_changes(self):
        report = self.report.score_regression
        self.assertEqual(report.matched_records, 4000)
        self.assertEqual(report.maximum_absolute_error, 0.0)
        self.assertEqual(report.mismatches, 0)


if __name__ == "__main__":
    unittest.main()
