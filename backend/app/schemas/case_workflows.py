"""Bounded case-scoped projections, never raw audit payloads or user records."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cases import CaseQuery, WorkbenchCase


class QueueQuery(CaseQuery):
    limit: int = Field(default=20, ge=1, le=50)


class QueueCase(WorkbenchCase):
    assigned_investigator: str | None
    review_recommendation: Literal["retain_human_review", "review_reduction_candidate"] | None
    assessment_version: int | None
    # Read-only display fields: the verified latest model score (0..1) and the time of the
    # newest event shown in the case's Activity History.
    assessment_score: float | None = None
    last_activity_at: datetime | None = None


class QueuePage(BaseModel):
    items: list[QueueCase]
    total: int
    limit: int
    offset: int


class DirectoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str = Field(default="", max_length=100)
    limit: int = Field(default=20, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=1000)


class Investigator(BaseModel):
    id: UUID
    username: str


class DirectoryPage(BaseModel):
    items: list[Investigator]
    total: int
    limit: int
    offset: int
    case_version: int


class ActivityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["all", "assignment"] = "all"
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=1000)


class ActivityItem(BaseModel):
    id: UUID
    case_id: UUID
    recorded_at: datetime
    event_type: str = Field(max_length=80)
    actor: Literal["you", "redacted", "system"]
    outcome: Literal[
        "recorded",
        "pending",
        "running",
        "completed",
        "failed",
        "retry_scheduled",
        "invalidated",
        "abstained",
    ]
    case_version: int | None = None
    duplicate_records: int | None = Field(default=None, ge=1)
    assessment_version: int | None = None
    evidence_revision: int | None = None
    access_revision: int | None = None
    assignment_change: Literal["assigned", "reassigned", "unassigned"] | None = None
    historical: Literal[True] = True


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    total: int
    limit: int
    offset: int
    case_version: int
    historical: Literal[True] = True
