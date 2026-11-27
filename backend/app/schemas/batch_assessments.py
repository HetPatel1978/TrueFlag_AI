"""Explicit batch requests and redacted live progress/results."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.assessments import SHA256, AssessmentDetail, Policy


class BatchAssessmentStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    start_assessment: Literal[True]
    import_validation_sha256: SHA256
    policy: Policy

    @field_validator("start_assessment", mode="before")
    @classmethod
    def explicit_start(cls, value):
        if value is not True:
            raise ValueError("Explicit Start Assessment is required")
        return value


class BatchProgress(BaseModel):
    batch_id: UUID
    import_id: UUID
    status: Literal[
        "dispatching", "processing", "completed", "partially_completed", "failed", "stopped"
    ]
    total_cases: int
    total_eligible_cases: int
    pending_dispatch: int
    queued: int
    running: int
    succeeded: int
    failed_manual_review: int
    skipped: int
    already_assessed: int
    retrying: int
    policy: Policy
    model_version: str
    model_sha256: str
    policy_version: str
    policy_sha256: str
    import_validation_sha256: str
    group_size: int
    backpressure_count: int
    reason_code: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    human_decision_required: Literal[True] = True


class BatchCaseResult(BaseModel):
    case_id: UUID
    source_row_number: int
    outcome: Literal[
        "pending_dispatch", "queued", "running", "succeeded", "failed_manual_review", "skipped"
    ]
    reason_code: str | None
    job_id: UUID | None
    retrying: bool
    attempts: int
    assessment: AssessmentDetail | None
    human_decision_required: Literal[True] = True


class BatchResultsPage(BaseModel):
    batch_id: UUID
    total: int
    offset: int
    limit: int
    items: list[BatchCaseResult]
