"""ID-and-policy aligned frozen-trace replay with explicit recommendation-only route mapping."""

import csv
import hashlib
import io
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from trueflag_ml.loader import DEFAULT_ROOT
from trueflag_ml.policy import (
    MODES,
    POLICY_SHA256,
    PolicyRecommendation,
    RiskPolicyEngine,
)
from trueflag_ml.regression import (
    RegressionError,
    RegressionReport,
    compare_results,
    load_evaluation,
)
from trueflag_ml.scoring import (
    MAX_BATCH_SIZE,
    RFScoringService,
    ScoringInputError,
    validate_record_id,
)
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION

TRACE_PATH = "validation/decision_traces.csv"
TRACE_SHA256 = "7db5506ca2745fe99ec0230831c3e59eceea8852daabb0983aa7135f6cef33b8"
LEGACY_ROUTES = {
    "Retain human review": "retain_human_review",
    "Dismiss": "review_reduction_candidate",
}
_FLAGS = (
    "score_based_retention",
    "coverage_protection",
    "coverage_changed_route",
    "manual_review_required",
)
_FIELDS = {
    "technical_row_id",
    "model_version",
    "pipeline_sha256",
    "policy_settings_sha256",
    "mode",
    "score",
    "threshold",
    "kycRiskScore",
    "priority_group",
    "score_based_retention",
    "coverage_protection",
    "coverage_changed_route",
    "execution_status",
    "final_route",
    "manual_review_required",
    "routing_reason",
}


@dataclass(frozen=True)
class PolicyTotals:
    policy: str
    retained: int
    review_reduction_candidates: int
    reference_retained: int
    reference_dismissed: int
    retained_difference: int
    dismissed_difference: int
    high_priority_overrides: int


@dataclass(frozen=True)
class PolicyComparison:
    matched_routes: int
    route_mismatches: int
    trace_mismatches: int
    processing_failures: int
    totals: tuple[PolicyTotals, ...]

    @property
    def passed(self):
        return (
            self.route_mismatches == self.trace_mismatches == self.processing_failures == 0
            and all(t.retained_difference == t.dismissed_difference == 0 for t in self.totals)
        )


@dataclass(frozen=True)
class PolicyRegressionReport:
    score_regression: RegressionReport
    policy_regression: PolicyComparison

    @property
    def passed(self):
        return self.score_regression.passed and self.policy_regression.passed


def load_policy_traces(artifact_root: Path | None = None):
    try:
        root = (DEFAULT_ROOT if artifact_root is None else Path(artifact_root)).resolve(strict=True)
        path = (root / TRACE_PATH).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise RegressionError("policy_trace_location_invalid")
        with path.open("rb") as stream:
            content = stream.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != TRACE_SHA256:
            raise RegressionError("policy_trace_integrity_failed")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""), strict=True)
        if set(reader.fieldnames or []) != _FIELDS or len(reader.fieldnames or []) != len(_FIELDS):
            raise RegressionError("policy_trace_schema_invalid")
        rows = list(reader)
        if len(rows) != 12000:
            raise RegressionError("policy_trace_count_invalid")
        return rows
    except FileNotFoundError:
        raise RegressionError("policy_trace_missing") from None
    except OSError:
        raise RegressionError("policy_trace_unreadable") from None
    except (UnicodeError, csv.Error):
        raise RegressionError("policy_trace_schema_invalid") from None


def _index_traces(rows, record_ids, settings):
    ids = tuple(record_ids)
    for ident in ids:
        try:
            validate_record_id(ident)
        except ScoringInputError:
            raise RegressionError("policy_record_ids_invalid") from None
    if not ids or len(set(ids)) != len(ids):
        raise RegressionError("policy_record_ids_invalid")
    expected = {(ident, mode) for ident in ids for mode in MODES}
    indexed = {}
    for row in rows:
        try:
            if set(row) != _FIELDS:
                raise RegressionError("policy_trace_schema_invalid")
            ident, mode = row["technical_row_id"], row["mode"]
            validate_record_id(ident)
            if mode not in MODES:
                raise RegressionError("policy_trace_mode_invalid")
            key = (ident, mode)
            if key in indexed:
                raise RegressionError("duplicate_policy_trace")
            if (
                row["model_version"] != MODEL_VERSION
                or row["pipeline_sha256"] != APPROVED_SHA256[MODEL_PATH]
                or row["policy_settings_sha256"] != POLICY_SHA256
            ):
                raise RegressionError("policy_trace_identity_invalid")
            score, threshold = float(row["score"]), float(row["threshold"])
            if (
                not math.isfinite(score)
                or not 0 <= score <= 1
                or threshold != settings.thresholds[mode]
            ):
                raise RegressionError("policy_trace_score_invalid")
            if row["kycRiskScore"] not in {str(value) for value in range(7)}:
                raise RegressionError("policy_trace_priority_invalid")
            kyc = int(row["kycRiskScore"])
            priority = "High" if kyc >= 3 else "Standard"
            if row["priority_group"] != priority:
                raise RegressionError("policy_trace_priority_invalid")
            if (
                any(row[name] not in {"True", "False"} for name in _FLAGS)
                or row["execution_status"] != "processed"
                or row["final_route"] not in LEGACY_ROUTES
            ):
                raise RegressionError("policy_trace_status_invalid")
            indexed[key] = {**row, "score": score, "threshold": threshold, "kycRiskScore": kyc}
        except (KeyError, TypeError, ValueError, ScoringInputError):
            raise RegressionError("policy_trace_schema_invalid") from None
    if set(indexed) != expected:
        raise RegressionError("policy_trace_ids_mismatch")
    return indexed


def compare_policy_results(rows, recommendations, record_ids, settings):
    references = _index_traces(rows, record_ids, settings)
    actual = {}
    for result in recommendations:
        if type(result) is not PolicyRecommendation:
            raise RegressionError("policy_result_schema_invalid")
        try:
            validate_record_id(result.record_id)
        except ScoringInputError:
            raise RegressionError("policy_result_schema_invalid") from None
        if type(result.selected_policy) is not str or result.selected_policy not in MODES:
            raise RegressionError("policy_result_schema_invalid")
        key = (result.record_id, result.selected_policy)
        if key in actual:
            raise RegressionError("duplicate_policy_result")
        actual[key] = result
    if set(actual) != set(references):
        raise RegressionError("policy_result_ids_mismatch")
    route_mismatches = trace_mismatches = failures = 0
    counts, ref_counts, overrides = Counter(), Counter(), Counter()
    for key, reference in references.items():
        result = actual[key]
        mode = key[1]
        ref_route = LEGACY_ROUTES[reference["final_route"]]
        ref_counts[mode, ref_route] += 1
        route_mismatches += result.recommended_route != ref_route
        processed = result.processing_status == "processed"
        failures += not processed
        if processed and result.recommended_route in LEGACY_ROUTES.values():
            counts[mode, result.recommended_route] += 1
            overrides[mode] += result.coverage_changed_route is True
        flags = (
            result.score_based_retention,
            result.coverage_protection,
            result.coverage_changed_route,
        )
        expected_flags = tuple(reference[name] == "True" for name in _FLAGS[:3])
        changed = reference["coverage_changed_route"] == "True"
        mismatch = (
            not processed
            or result.policy_version != settings.version
            or result.policy_sha256 != POLICY_SHA256
            or result.model_version != MODEL_VERSION
            or result.model_sha256 != APPROVED_SHA256[MODEL_PATH]
            or result.threshold != reference["threshold"]
            or type(result.kyc_risk_score) is not int
            or result.kyc_risk_score != reference["kycRiskScore"]
            or result.priority_group != reference["priority_group"]
            or type(result.model_score) is not float
            or not 0 <= result.model_score <= 1
            or not math.isfinite(result.model_score)
            or abs(result.model_score - reference["score"]) > 1e-12
            or flags != expected_flags
            or any(type(flag) is not bool for flag in flags)
            or result.override_reason != ("coverage_high_priority_protection" if changed else None)
            or result.routing_reason != reference["routing_reason"]
            or result.human_decision_required is not True
            or (result.recommended_route == "retain_human_review")
            != (reference["manual_review_required"] == "True")
        )
        trace_mismatches += bool(mismatch)
    totals = tuple(
        PolicyTotals(
            policy=mode,
            retained=counts[mode, "retain_human_review"],
            review_reduction_candidates=counts[mode, "review_reduction_candidate"],
            reference_retained=ref_counts[mode, "retain_human_review"],
            reference_dismissed=ref_counts[mode, "review_reduction_candidate"],
            retained_difference=counts[mode, "retain_human_review"]
            - ref_counts[mode, "retain_human_review"],
            dismissed_difference=counts[mode, "review_reduction_candidate"]
            - ref_counts[mode, "review_reduction_candidate"],
            high_priority_overrides=overrides[mode],
        )
        for mode in MODES
    )
    return PolicyComparison(len(references), route_mismatches, trace_mismatches, failures, totals)


def run_policy_regression(artifact_root: Path | None = None):
    engine = RiskPolicyEngine(artifact_root)
    if not engine.ready:
        raise RegressionError("policy_unavailable")
    evaluation = load_evaluation(artifact_root)
    traces = load_policy_traces(artifact_root)
    references = _index_traces(traces, (r.record_id for r in evaluation.records), engine.settings)
    scorer = RFScoringService(artifact_root)
    scores = []
    for start in range(0, len(evaluation.records), MAX_BATCH_SIZE):
        scores.extend(scorer.score_batch(evaluation.records[start : start + MAX_BATCH_SIZE]))
    score_report = compare_results(evaluation.reference_scores, scores)
    records = {r.record_id: r for r in evaluation.records}
    for (ident, _), trace in references.items():
        if (
            trace["score"] != evaluation.reference_scores[ident]
            or trace["kycRiskScore"] != records[ident].features["kycRiskScore"]
        ):
            raise RegressionError("policy_trace_input_mismatch")
    recommendations = [
        engine.evaluate(
            score, mode, kyc_risk_score=records[score.record_id].features["kycRiskScore"]
        )
        for score in scores
        for mode in MODES
    ]
    policy_report = compare_policy_results(traces, recommendations, records, engine.settings)
    return PolicyRegressionReport(score_report, policy_report)
