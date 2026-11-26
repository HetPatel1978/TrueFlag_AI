"""Human review intake with binding/provenance gates; no synthetic labels become human truth."""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.assessments import SHA256
from app.schemas.evidence_read import Contract
from app.services.ingestion import digest

from .dataset import rubric


class HumanReview(Contract):
    rubric_version: Literal["trueflag.ai-evaluation-rubric.v1"]
    dataset_sha256: SHA256
    report_sha256: SHA256
    review_dossier_sha256: SHA256
    response_sha256: SHA256
    case_key: str = Field(min_length=1, max_length=100)
    reviewer_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    source: Literal["human_submitted", "synthetic_test_fixture"]
    independence_attestation: Literal[True]
    qualifications_reference: str = Field(min_length=1, max_length=200)
    submitted_at: AwareDatetime
    scores: dict[str, int | None]
    rationale: str = Field(min_length=1, max_length=2000)
    uncertainty: Literal["assessed", "unable_to_assess", "needs_adjudication"]

    @model_validator(mode="before")
    @classmethod
    def strict_scores(cls, value):
        if type(value) is not dict or type(value.get("independence_attestation")) is not bool:
            raise ValueError("review_attestation_required")
        scores = value.get("scores", {})
        if set(scores) != set(rubric()["dimensions"]) or any(
            v is not None and (type(v) is not int or not 0 <= v <= 3) for v in scores.values()
        ):
            raise ValueError("review_scores_invalid")
        return value


def review_tasks(report):
    return dict(
        rubric_version=rubric()["version"],
        dataset_sha256=report["dataset_sha256"],
        report_sha256=digest(report),
        review_dossier_sha256=report["review_dossier_sha256"],
        review_status="unreviewed",
        reviewer_id=None,
        independence_attestation=None,
        tasks=[
            dict(
                case_key=r["case_key"],
                response_sha256=r["response_sha256"],
                scores={key: None for key in rubric()["dimensions"]},
                rationale=None,
                uncertainty=None,
            )
            for r in report["results"]
            if r.get("control") == "baseline"
        ],
        semantic_support_score=None,
        unsupported_factual_claim_rate=None,
        notice="Engineering checks do not supply independent semantic labels.",
    )


def validate_review(review, report, registry):
    item = (
        HumanReview.model_validate_json(review.model_dump_json())
        if isinstance(review, HumanReview)
        else HumanReview.model_validate(review)
    )
    if (
        item.source != "human_submitted"
        or registry.get("registry_status") != "approved_by_human_owner"
        or item.reviewer_id not in registry.get("authorized_reviewers", [])
    ):
        raise ValueError("independent_reviewer_not_approved")
    if item.reviewer_id in {
        "model_under_test",
        "controlled_fixture_author",
        "engineering_reference_author",
    }:
        raise ValueError("reviewer_independence_not_established")
    if (
        item.dataset_sha256 != report["dataset_sha256"]
        or item.review_dossier_sha256 != report["review_dossier_sha256"]
        or item.report_sha256 != digest(report)
        or (item.case_key, item.response_sha256)
        not in {(r["case_key"], r["response_sha256"]) for r in report["results"]}
    ):
        raise ValueError("review_binding_mismatch")
    return dict(
        review_sha256=digest(item.model_dump(mode="json")),
        status="human_submission_requires_adjudication",
        reviewer_id=item.reviewer_id,
        semantic_quality_approved=False,
    )


def review_event(review, report, registry, previous_sha256=None):
    # Local append-only artifact chain; not a cryptographic identity/authentication service.
    result = validate_review(review, report, registry)
    body = dict(previous_sha256=previous_sha256, **result)
    return dict(**body, event_sha256=digest(body))
