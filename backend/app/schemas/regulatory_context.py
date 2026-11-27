"""Dormant investigator handoff: approved source context, never a legal conclusion."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.assessments import SHA256
from app.schemas.references import Citation, Contract, ReferenceResult


class RegulatoryPassage(Contract):
    source_id: UUID
    source_key: str
    version_manifest_sha256: SHA256
    approval_id: UUID
    reviewer_reference: UUID
    review_reference_sha256: SHA256 | None
    review_kind: Literal["human", "test_fixture"]
    citation: Citation
    content_trust: Literal["untrusted_reference_data"] = "untrusted_reference_data"


class RegulatoryContext(Contract):
    schema_version: Literal["trueflag.regulatory-investigation-context.v1"] = (
        "trueflag.regulatory-investigation-context.v1"
    )
    case_id: UUID
    result: ReferenceResult
    sources: tuple[RegulatoryPassage, ...] = Field(max_length=5)
    context_sha256: SHA256
    use: Literal["regulatory_context_human_review_required"] = (
        "regulatory_context_human_review_required"
    )
    can_establish_customer_violation: Literal[False] = False
    can_execute_instructions: Literal[False] = False
    must_revalidate_before_publication: Literal[True] = True

    @model_validator(mode="after")
    def membership(self):
        if list(self.result.passages) != [s.citation for s in self.sources]:
            raise ValueError("regulatory_context_membership_mismatch")
        return self
