"""Versioned regulatory handoff; source context never establishes a case violation."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.assessments import SHA256
from app.schemas.evidence_read import Contract, SnapshotIdentity
from app.schemas.investigation_drafts import DraftBody, ProviderInput, ProviderProposal
from app.schemas.provider_live import AIDraftBody, AIProposal
from app.schemas.references import Citation, ReferenceQuery, ReferenceResult
from app.schemas.regulatory_context import RegulatoryContext


class InvestigationRegulatoryContext(Contract):
    schema_version: Literal["trueflag.investigation-regulatory.v1"] = (
        "trueflag.investigation-regulatory.v1"
    )
    case_id: UUID
    investigation_run_id: UUID
    packet_id: UUID
    packet_sha256: SHA256
    result: ReferenceResult
    query: ReferenceQuery
    grounding: RegulatoryContext | None
    binding_sha256: SHA256
    snapshot: SnapshotIdentity
    grant_revision: int | None = Field(ge=1)
    clock_epoch: int = Field(ge=1)
    prepared_second: int
    expires_second: int
    legal_correctness_verified: Literal[False] = False
    must_revalidate_before_dispatch_and_publication: Literal[True] = True


class GroundedProviderInput(ProviderInput):
    regulatory_context: Literal["approved_context_human_review_required"] = (
        "approved_context_human_review_required"
    )
    regulatory_binding_sha256: SHA256
    regulatory_passages: list[Citation] = Field(min_length=1, max_length=5)
    reference_text_is_untrusted: Literal[True] = True


class GroundedAIProposal(AIProposal):
    regulatory_binding_sha256: SHA256
    regulatory_citations: list[UUID] = Field(max_length=5)


class GroundedSimulationProposal(ProviderProposal):
    regulatory_binding_sha256: SHA256
    regulatory_citations: list[UUID] = Field(max_length=5)


class GroundedDraftBody(DraftBody):
    regulatory_context: Literal["approved_context_human_review_required"] = (
        "approved_context_human_review_required"
    )
    regulatory_binding_sha256: SHA256
    regulatory_citations: list[Citation] = Field(max_length=5)


class GroundedAIDraftBody(AIDraftBody):
    regulatory_context: Literal["approved_context_human_review_required"] = (
        "approved_context_human_review_required"
    )
    regulatory_binding_sha256: SHA256
    regulatory_citations: list[Citation] = Field(max_length=5)
