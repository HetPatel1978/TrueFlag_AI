"""Strict deterministic packets, never provider drafts or case decisions."""

from datetime import timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.assessments import SHA256, AssessmentDetail
from app.schemas.evidence import Currency
from app.schemas.evidence_read import (
    AnalyticsResult,
    Contract,
    Coverage,
    EvidenceReference,
    SnapshotIdentity,
    SourceReference,
    TransactionItem,
    Window,
)

COORDINATOR_VERSION = "trueflag.evidence-investigation.v1"
VERIFIER_VERSION = "trueflag.source-packet-verifier.v1"
Code = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")]


class InvestigationRequest(Contract):
    expected_case_version: int = Field(strict=True, ge=1)
    expected_evidence_revision: int = Field(strict=True, ge=0)
    expected_access_revision: int = Field(strict=True, ge=0)
    assessment_id: UUID | None = None
    without_assessment_reason: Literal["not_selected", "unavailable"] | None = None
    window: Window
    currencies: tuple[Currency, ...] = Field(min_length=1, max_length=4)
    question_template: Literal["evidence_review_v1"] = "evidence_review_v1"

    @field_validator("window")
    @classmethod
    def utc_window(cls, value):
        return Window(
            start=value.start.astimezone(timezone.utc), end=value.end.astimezone(timezone.utc)
        )

    @model_validator(mode="after")
    def selection(self):
        if (self.assessment_id is None) != (self.without_assessment_reason is not None):
            raise ValueError("Explicit assessment or omission reason required")
        if len(set(self.currencies)) != len(self.currencies):
            raise ValueError("Duplicate currency")
        return self


class InputManifest(Contract):
    coordinator_version: Literal["trueflag.evidence-investigation.v1"] = COORDINATOR_VERSION
    calculation_version: Literal["trueflag.transaction-analytics.v1"] = (
        "trueflag.transaction-analytics.v1"
    )
    verifier_version: Literal["trueflag.source-packet-verifier.v1"] = VERIFIER_VERSION
    actor_id: UUID
    case_id: UUID
    alert_id: UUID
    alert_feature_hash_schema: Literal["trueflag.investigation-alert-fingerprint.v1"] = (
        "trueflag.investigation-alert-fingerprint.v1"
    )
    alert_feature_fingerprint_sha256: SHA256
    request: InvestigationRequest
    snapshot: SnapshotIdentity
    sources: list[SourceReference] = Field(max_length=10)
    evidence: list[EvidenceReference] = Field(max_length=200)
    assessment_sha256: SHA256 | None


class PacketContext(Contract):
    case_id: UUID
    state: str = Field(max_length=30)
    human_disposition: str | None = Field(max_length=30)
    available_categories: list[Code] = Field(max_length=4)
    missing_categories: list[Code] = Field(max_length=4)


class FinancialFact(Contract):
    reference_id: UUID
    input_record_ids: list[UUID] = Field(max_length=200)
    coverage: Coverage
    result: AnalyticsResult


class InvestigationPacketBody(Contract):
    coordinator_version: Literal["trueflag.evidence-investigation.v1"] = COORDINATOR_VERSION
    run_id: UUID
    manifest_sha256: SHA256
    mode: Literal["deterministic_evidence_only"] = "deterministic_evidence_only"
    outcome: Literal["packet_ready", "abstained"]
    context: PacketContext
    transactions: list[TransactionItem] = Field(max_length=200)
    facts: list[FinancialFact] = Field(max_length=8)
    model_signal: AssessmentDetail | None
    model_interpretation: Literal["model_signal_not_fact_or_proof_of_crime"] = (
        "model_signal_not_fact_or_proof_of_crime"
    )
    evidence: list[EvidenceReference] = Field(max_length=200)
    missing_evidence: list[Code] = Field(max_length=20)
    conflicts: list[Code] = Field(max_length=10)
    limitations: list[Code] = Field(max_length=30)
    questions: list[Code] = Field(max_length=20)
    abstentions: list[Code] = Field(min_length=1, max_length=20)
    human_review_required: Literal[True] = True
    regulatory_citations: tuple[()] = ()
    provider_used: Literal[False] = False
