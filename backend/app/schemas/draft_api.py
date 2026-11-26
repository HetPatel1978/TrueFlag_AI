"""Strict provider-specific reader projections; no arbitrary provider or worker metadata."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.assessments import SHA256, AssessmentDetail
from app.schemas.evidence_read import Contract, TransactionItem
from app.schemas.investigation_drafts import ProposedHypothesis
from app.schemas.investigations import Code, FinancialFact, InvestigationRequest
from app.schemas.references import Citation, ReferenceQuery
from app.schemas.research_demo import (
    NOTICE,
    FindingCitation,
    ResearchCitation,
    ResearchExcerptCitation,
    ResearchRetrieval,
    ResearchRetrievalV2,
    ResearchRetrievalV3,
    ResearchSourceText,
)


class DraftRequestInput(Contract):
    investigation_run_id: UUID
    expected_packet_sha256: SHA256
    provider: Literal["simulation", "claude"] = "simulation"
    regulatory_query: ReferenceQuery | None = None


class DraftStatus(Contract):
    draft_run_id: UUID
    status: Literal["pending", "running", "succeeded", "abstained", "failed", "invalidated"]
    attempts: int = Field(ge=0, le=3)
    error_code: Code | None
    mode: Literal["offline_simulation", "claude_live"] = "offline_simulation"
    live_provider_used: bool = False
    human_review_required: Literal[True] = True


class DraftStartInput(Contract):
    investigation_request: InvestigationRequest
    provider: Literal["auto", "simulation", "claude"] = "auto"
    regulatory_query: ReferenceQuery | None = None


class DraftStartStatus(DraftStatus):
    investigation_run_id: UUID


class Finding(Contract):
    reference_id: UUID
    supporting_evidence: list[UUID] = Field(max_length=200)
    contradictory_evidence: list[UUID] = Field(max_length=200)


class ObservedFinding(Finding):
    claim_type: Literal["observed_fact"]
    summary: TransactionItem


class CalculatedFinding(Finding):
    claim_type: Literal["calculated_fact"]
    summary: FinancialFact


class ModelFinding(Finding):
    claim_type: Literal["model_signal"]
    summary: AssessmentDetail


class SimulationProvenance(Contract):
    provider: Literal["deterministic_fake"]
    model: Literal["trueflag-fake-selection.v1"]
    prompt_version: Literal["trueflag.evidence-only-prompt.v1"]
    prompt_sha256: SHA256
    configuration_sha256: SHA256
    parent_manifest_sha256: SHA256


class SimulationDraft(Contract):
    content_sha256: SHA256
    draft_run_id: UUID
    investigation_run_id: UUID
    manifest_sha256: SHA256
    packet_sha256: SHA256
    outcome: Literal["draft_ready", "abstained"]
    findings: list[
        Annotated[
            ObservedFinding | CalculatedFinding | ModelFinding, Field(discriminator="claim_type")
        ]
    ] = Field(max_length=20)
    hypotheses: list[ProposedHypothesis] = Field(max_length=8)
    questions: list[Code] = Field(max_length=20)
    unresolved_questions: list[Code] = Field(max_length=20)
    next_steps: list[Code] = Field(max_length=4)
    missing_evidence: list[Code] = Field(max_length=20)
    conflicts: list[Code] = Field(max_length=10)
    limitations: list[Code] = Field(max_length=30)
    provenance: SimulationProvenance
    verification: Literal["source_reference_numeric_checks_passed"]
    semantic_review: Literal["pending_human_review"] = "pending_human_review"
    regulatory_context: Literal[
        "unavailable_unapproved", "approved_context_human_review_required"
    ] = "unavailable_unapproved"
    regulatory_citations: list[Citation] = Field(default_factory=list, max_length=5)
    simulation: Literal[True] = True
    live_provider_used: Literal[False] = False


class ClaudeProvenance(Contract):
    provider: Literal["anthropic"]
    model: Literal["claude-sonnet-5-5"]
    prompt_version: Literal["trueflag.ai-evidence-prompt.v1"]
    prompt_sha256: SHA256
    configuration_sha256: SHA256
    parent_manifest_sha256: SHA256


class LiveDraft(SimulationDraft):
    provenance: ClaudeProvenance
    simulation: Literal[False] = False
    live_provider_used: Literal[True] = True


class ResearchLiveDraft(LiveDraft):
    regulatory_context: Literal["research_unapproved"] = "research_unapproved"
    regulatory_citations: list[ResearchExcerptCitation | ResearchCitation] = Field(
        default_factory=list, max_length=3
    )
    research_notice: Literal[NOTICE] = NOTICE
    publication_approved: Literal[False] = False
    # Verified finding->source links (v3 runs only; earlier runs cite the overall conclusion).
    finding_citations: list[FindingCitation] = Field(default_factory=list, max_length=40)
    # v3 records carry the relative-score threshold; v2 records keep the original shape.
    # v4 runs add the excerpt sent per source.
    retrieval: ResearchRetrievalV3 | ResearchRetrievalV2 | ResearchRetrieval | None = None
    # Full hash-verified text of every retrieved section (read display only; never sent).
    source_texts: list[ResearchSourceText] = Field(default_factory=list, max_length=3)


class DraftDetail(DraftStatus):
    draft: SimulationDraft | LiveDraft | ResearchLiveDraft | None = None


class DraftHistoryItem(DraftStatus):
    investigation_run_id: UUID
    created_at: datetime
    manifest_sha256: SHA256
    case_version: int = Field(ge=1)
    evidence_revision: int = Field(ge=0)
    access_revision: int = Field(ge=0)
    validation_status: Literal["stored_not_revalidated"] = "stored_not_revalidated"


class DraftHistory(Contract):
    items: list[DraftHistoryItem] = Field(max_length=20)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=1000)
