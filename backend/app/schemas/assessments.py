"""Public allowlisted contracts; no predictor values, worker secrets or internal receipts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.alerts import AlertFeatures

SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Policy = Literal["Efficiency", "Balanced", "Coverage"]
Route = Literal["retain_human_review", "review_reduction_candidate"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AssessmentRequest(Contract):
    expected_version: int = Field(strict=True, ge=1, le=2147483647)
    run_id: UUID
    policy: Policy


class AssessmentQuery(Contract):
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class JobStatus(Contract):
    job_id: UUID
    case_id: UUID
    run_id: UUID
    status: Literal["pending", "running", "succeeded", "failed"]
    attempts: int = Field(ge=0, le=3)
    policy: Policy
    assessment_id: UUID | None
    failure_code: (
        Literal[
            "execution_timeout",
            "child_failed",
            "invalid_child_output",
            "lease_expired",
            "database_unavailable",
            "processing_unavailable",
            "authorization_changed",
            "stale_case",
        ]
        | None
    )
    fallback_route: Literal["manual_review"] | None
    human_decision_required: Literal[True]


class AssessmentSummary(Contract):
    assessment_id: UUID
    case_id: UUID
    alert_id: UUID
    run_id: UUID
    version: int = Field(ge=1)
    case_version: int = Field(ge=1)
    status: Literal["completed"]
    processed_at: datetime
    score: float = Field(ge=0, le=1)
    model_version: str = Field(max_length=100)
    model_sha256: SHA256
    selected_policy: Policy
    policy_version: str = Field(max_length=100)
    recommended_route: Route
    input_sha256: SHA256
    content_sha256: SHA256
    human_decision_required: Literal[True]


class AssessmentPage(Contract):
    items: list[AssessmentSummary] = Field(max_length=50)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    offset: int = Field(ge=0, le=10000)


class InputProvenance(Contract):
    hash_schema: str = Field(max_length=100)
    ingestion_input_sha256: SHA256
    feature_contract_version: str = Field(max_length=100)
    contract_sha256: SHA256


class PolicyTrace(Contract):
    policy_sha256: SHA256
    threshold: float = Field(ge=0, le=1)
    priority_group: Literal["Standard", "High"]
    override_reason: Literal["coverage_high_priority_protection"] | None
    routing_reason: str = Field(max_length=100)
    score_based_retention: bool
    coverage_protection: bool
    coverage_changed_route: bool


class Contribution(Contract):
    name: str = Field(max_length=80)
    contribution: float
    direction: Literal["raises_score", "lowers_score", "no_contribution"]
    missing: bool


class ExplanationMethod(Contract):
    algorithm: Literal["Exact TreeSHAP"]
    library_version: Literal["0.51.0"]
    feature_perturbation: Literal["tree_path_dependent"]
    model_output_argument: Literal["raw"]
    output_space: Literal["SAR-positive predict_proba score"]
    positive_class_label: Literal[1]
    positive_class_index: Literal[1]
    approximate: Literal[False]
    background: Literal["fitted_tree_path_counts"]


class Verification(Contract):
    status: Literal["verified"]
    verifier: Literal["trueflag.independent-explanation.v1"]
    score_atol: Literal[1e-12]
    group_atol: Literal[1e-12]
    reconstruction_atol: Literal[1e-6]
    rtol: Literal[0]
    independent_model_and_root_checks: Literal[True]
    runtime_dependencies: dict[str, str] = Field(max_length=16)
    approved_artifact_identities: dict[str, SHA256] = Field(max_length=8)


class VerifiedExplanation(Contract):
    status: Literal["verified"]
    base_value: float
    features: list[Contribution] = Field(min_length=27, max_length=27)
    ranking: list[str] = Field(min_length=27, max_length=27)
    top_features: list[str] = Field(max_length=3)
    other_features_contribution: float
    reconstruction_residual: float
    method: ExplanationMethod
    verification: Verification

    @model_validator(mode="after")
    def approved_fields(self):
        names = tuple(AlertFeatures.model_fields)
        if (
            tuple(f.name for f in self.features) != names
            or set(self.ranking) != set(names)
            or not set(self.top_features).issubset(names)
        ):
            raise ValueError("Invalid contribution contract")
        return self


class AssessmentDetail(AssessmentSummary):
    input_provenance: InputProvenance
    policy_trace: PolicyTrace
    explanation: VerifiedExplanation
