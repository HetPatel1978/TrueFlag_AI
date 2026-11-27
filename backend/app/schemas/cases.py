from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.alerts import AlertFeatures

CaseStatus = Literal["open", "in_review", "awaiting_approval", "closed"]


class CaseQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_session_id: UUID | None = None
    origin: Literal["all", "uploaded"] = "all"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
    status: CaseStatus | None = None
    assigned_to: UUID | None = None
    assignment: Literal["all", "assigned", "unassigned"] = "all"
    sort_by: Literal["created_at", "status", "version"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"
    search: str = Field(default="", max_length=128)
    priority: Literal["Standard", "High"] | None = None
    assessment_status: (
        Literal["not_requested", "pending", "running", "succeeded", "failed"] | None
    ) = None
    queue: Literal["all", "my", "unassigned", "review", "processing"] = "all"

    @model_validator(mode="after")
    def coherent_filters(self):
        if self.assigned_to is not None and self.assignment == "unassigned":
            raise ValueError("An assignee filter cannot select unassigned cases")
        return self


class CaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    alert_id: UUID
    assigned_to: UUID | None
    status: CaseStatus
    disposition: Literal["close", "recommend"] | None
    version: int
    created_at: datetime


class WorkbenchCase(CaseSummary):
    source_id: str
    priority: Literal["Standard", "High"]
    assessment_status: Literal["not_requested", "pending", "running", "succeeded", "failed"]
    latest_job_id: UUID | None


class CasePage(BaseModel):
    items: list[WorkbenchCase]
    total: int
    limit: int
    offset: int


class CaseAlert(BaseModel):
    source_id: str
    data_classification: Literal["synthetic"]
    feature_contract_version: Literal["datarobot_provisional_v1"]
    features: AlertFeatures


class CaseDetail(CaseSummary):
    alert: CaseAlert


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_to: UUID | None
    expected_version: int = Field(strict=True, ge=1, le=2147483646)
