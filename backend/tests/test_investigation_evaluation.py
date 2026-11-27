"""Offline evaluator units. No network, database or model execution."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.evaluation.dataset import case_provenance, dataset, rubric, source_bundle
from app.evaluation.harness import blocked_fixture, run_offline, write_once
from app.evaluation.metrics import aggregate, operation_observation
from app.evaluation.oracles import requires_abstention
from app.evaluation.review import HumanReview, review_event, review_tasks, validate_review
from app.services.connected_scenarios import expected_activity
from app.services.ingestion import digest


def test_dataset_partitions_seeds_provenance_and_semantic_truth_are_separate():
    value = dataset()
    assert len(value["cases"]) == 36
    dev = [case_provenance(c) for c in value["cases"] if c["split"] == "development"]
    held = [case_provenance(c) for c in value["cases"] if c["split"] == "heldout"]
    assert len({c["bundle_sha256"] for c in dev + held}) == 36
    assert {c["case_key"] for c in dev}.isdisjoint(c["case_key"] for c in held)
    assert all(c["labels"] == "engineering_reference_only" for c in dev + held)
    assert [case_provenance(c) for c in value["cases"]] == [
        case_provenance(c) for c in dataset()["cases"]
    ]


@pytest.mark.parametrize("split", ["development", "heldout"])
def test_missing_materialization_never_counts_as_success(tmp_path, split):
    report, tasks = run_offline(tmp_path, split=split)
    assert report["evaluation_status"] == "blocked_or_failed" and report["planned_cases"] == 18
    assert report["metrics"]["evaluated_responses"] == 0
    assert report["metrics"]["evidence_reference_validity_rate"] is None
    assert report["metrics"]["semantic_support_score"] is None and tasks["tasks"] == []


def test_blocked_clock_case_excluded_with_explicit_denominator(tmp_path):
    spec = dataset()["cases"][0]
    write_once(tmp_path / (spec["case_key"] + ".json"), blocked_fixture(spec, "clock_unavailable"))
    report, _ = run_offline(tmp_path, split=spec["split"])
    assert report["metrics"]["blocked_or_unavailable_cases"] == 18
    assert any(r.get("failure_class") == "clock_unavailable" for r in report["results"])
    assert report["live_provider_requests"] == 0


def test_artifacts_are_append_only_and_integrity_checked(tmp_path):
    spec = dataset()["cases"][0]
    path = tmp_path / (spec["case_key"] + ".json")
    value = blocked_fixture(spec, "clock_unavailable")
    write_once(path, value)
    with pytest.raises(FileExistsError):
        write_once(path, value)
    value["bundle_sha256"] = "a" * 64
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="integrity_failed"):
        run_offline(tmp_path, split="development")


def test_missing_income_zero_reversals_and_currency_oracles():
    specs = {c["category"]: c for c in dataset()["cases"] if c["split"] == "heldout"}
    missing = source_bundle(specs["missing_income"])
    zero = source_bundle(specs["zero_income"])
    assert next(r.annual_income for r in missing.records if r.kind == "customer") is None
    assert next(r.annual_income for r in zero.records if r.kind == "customer") == 0
    reverse = source_bundle(specs["reversals"])
    gross = expected_activity(reverse)
    net = expected_activity(reverse, net=True)
    assert gross["count"] == 13 and net["count"] == 11
    multi = source_bundle(specs["multi_currency"])
    assert expected_activity(multi, currency="USD")["count"] == 6
    assert expected_activity(multi, currency="CAD")["count"] == 6
    assert requires_abstention(source_bundle(specs["inconclusive"]))
    assert requires_abstention(source_bundle(specs["conflicting_information"]))


@pytest.mark.parametrize(
    "status", ["completed", "timeout", "cancelled", "rate_limited", "failed", "incomplete"]
)
def test_operational_fixture_accounting_is_not_real_provider_measurement(status):
    item = operation_observation(
        mode="controlled_offline_fixture",
        status=status,
        elapsed_ms=12,
        input_tokens=100,
        output_tokens=50,
        input_rate="1",
        output_rate="2",
    )
    assert item["configured_fixture_cost_estimate_usd"] == "0.0002"
    assert item["real_inference_measured"] is False and item["vendor_usage_verified"] is False


@pytest.mark.parametrize(
    "change",
    [
        dict(mode="live"),
        dict(elapsed_ms=float("nan")),
        dict(input_tokens=True),
        dict(input_rate="NaN"),
    ],
)
def test_accounting_rejects_fake_live_claims_or_invalid_values(change):
    args = dict(
        mode="controlled_offline_fixture",
        status="completed",
        elapsed_ms=12,
        input_tokens=10,
        output_tokens=1,
        input_rate="1",
        output_rate="2",
    )
    args.update(change)
    with pytest.raises(ValueError):
        operation_observation(**args)


def report_and_review():
    report = dict(
        dataset_sha256="a" * 64,
        review_dossier_sha256="d" * 64,
        results=[dict(case_key="heldout-ordinary", response_sha256="b" * 64, control="baseline")],
    )
    review = dict(
        rubric_version=rubric()["version"],
        dataset_sha256="a" * 64,
        report_sha256=digest(report),
        review_dossier_sha256=report["review_dossier_sha256"],
        response_sha256="b" * 64,
        case_key="heldout-ordinary",
        reviewer_id="external_reviewer",
        source="human_submitted",
        independence_attestation=True,
        qualifications_reference="operator-held-qualification-dossier",
        submitted_at=datetime.now(timezone.utc),
        scores={name: None for name in rubric()["dimensions"]},
        rationale="Insufficient independent review; synthetic contract test only.",
        uncertainty="unable_to_assess",
    )
    return report, review


def test_independent_review_template_blank_and_registry_unapproved():
    report, review = report_and_review()
    template = review_tasks(report)
    assert template["review_status"] == "unreviewed" and template["reviewer_id"] is None
    assert all(value is None for value in template["tasks"][0]["scores"].values())
    with pytest.raises(ValueError, match="not_approved"):
        validate_review(review, report, rubric())


@pytest.mark.parametrize(
    "change",
    [
        dict(source="synthetic_test_fixture"),
        dict(report_sha256="c" * 64),
        dict(reviewer_id="model_under_test"),
    ],
)
def test_self_review_synthetic_labels_and_stale_bindings_cannot_certify(change):
    report, review = report_and_review()
    review.update(change)
    registry = dict(
        registry_status="approved_by_human_owner",
        authorized_reviewers=["external_reviewer", "model_under_test"],
    )
    with pytest.raises(ValueError):
        validate_review(review, report, registry)


def test_review_events_bind_exact_run_and_do_not_approve_quality():
    report, review = report_and_review()
    registry = dict(
        registry_status="approved_by_human_owner", authorized_reviewers=["external_reviewer"]
    )
    result = review_event(review, report, registry)
    assert result["semantic_quality_approved"] is False
    assert result["status"] == "human_submission_requires_adjudication"
    second = review_event(review, report, registry, result["event_sha256"])
    assert second["previous_sha256"] == result["event_sha256"]
    review["scores"]["semantic_support"] = True
    with pytest.raises(ValidationError):
        HumanReview.model_validate(review)


def test_unmeasured_semantics_and_operations_stay_null_in_aggregate():
    metrics = aggregate([])
    for key in [
        "real_model_injection_resistance",
        "unsupported_factual_claim_rate",
        "real_provider_cost_per_investigation_usd",
        "real_provider_latency_ms",
        "reasoning_quality",
    ]:
        assert metrics[key] is None
