"""Bounded human commands. No model execution or automatic dispositions."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, RootModel, TypeAdapter, field_validator

from app.schemas.assessments import SHA256
from app.schemas.evidence_read import Contract, EvidenceReference, Token

Text = Annotated[str, Field(strict=True, min_length=10, max_length=4000)]
Outcome = Literal[
    "additional_review_required",
    "no_further_action_recommended",
    "escalated_for_compliance_review",
    "investigation_completed",
]
POLICY = "trueflag.human-casework.v1"


class Command(Contract):
    snapshot: Token
    expected_revision: int = Field(strict=True, ge=0, le=1000)
    rationale: Text
    supporting_records: list[EvidenceReference] = Field(default_factory=list, max_length=10)

    @field_validator("rationale")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10 or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("A meaningful plain-text rationale is required")
        return value.strip()


class Note(Command):
    kind: Literal["note"]
    parent_id: UUID | None = None


class InformationRequest(Command):
    kind: Literal["information_request"]
    category: Literal[
        "customer_documentation",
        "account_information",
        "transaction_clarification",
        "relationship_verification",
        "activity_history",
    ]
    due_date: date | None = Field(default=None, strict=True)
    responsible_party: Literal["assigned_analyst", "supervisor"] = "assigned_analyst"


class InformationResponse(Command):
    kind: Literal["information_response"]
    parent_id: UUID
    status: Literal["resolved", "cancelled"]


class FindingReview(Command):
    kind: Literal["finding_review"]
    draft_run_id: UUID
    reference_id: UUID
    expected_draft_sha256: SHA256
    decision: Literal["accept_for_consideration", "reject", "defer", "further_investigation"]


class Escalation(Command):
    kind: Literal["escalation"]


class SupervisorResponse(Command):
    kind: Literal["supervisor_response"]
    parent_id: UUID
    decision: Literal["approve_resolution", "return_for_investigation"]
    proposed_outcome: Outcome


class Resolution(Command):
    kind: Literal["resolution"]
    parent_id: UUID
    outcome: Outcome
    confirmed: Literal[True]


Action = Annotated[
    Note
    | InformationRequest
    | InformationResponse
    | FindingReview
    | Escalation
    | SupervisorResponse
    | Resolution,
    Field(discriminator="kind"),
]
ACTION = TypeAdapter(Action)


class ActionBody(RootModel[Action]):
    pass


class Entry(Contract):
    id: UUID
    case_id: UUID
    actor_id: UUID
    author: str
    recorded_at: datetime
    revision: int
    kind: str
    parent_id: UUID | None
    content_sha256: SHA256
    payload: dict | None
    binding: dict | None
    content_status: Literal["available", "withheld_source_changed"]
    immutable: Literal[True] = True


class CaseworkPage(Contract):
    items: list[Entry] = Field(max_length=20)
    total: int
    revision: int
    limit: int
    offset: int
    open_information_requests: int
    pending_escalations: int
    resolution: Outcome | None
    policy_version: Literal[POLICY] = POLICY
    allowed_resolutions: list[Outcome]
