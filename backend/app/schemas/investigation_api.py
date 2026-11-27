"""Allowlisted evidence-only gateway contracts; no worker secrets or predictor values."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.evidence_read import Contract
from app.schemas.investigations import InvestigationPacketBody


class InvestigationStatus(Contract):
    run_id: UUID
    status: Literal["pending", "running", "succeeded", "abstained", "failed", "invalidated"]
    attempts: int = Field(ge=0, le=3)
    error_code: (
        Literal[
            "lease_expired",
            "execution_timeout",
            "processing_unavailable",
            "verification_failed",
            "input_invalidated",
            "authorization_revoked",
            "worker_revoked",
            "resource_limit",
        ]
        | None
    )
    human_review_required: Literal[True] = True
    mode: Literal["deterministic_evidence_only"] = "deterministic_evidence_only"


class InvestigationHistoryItem(InvestigationStatus):
    created_at: datetime
    manifest_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    assessment_id: UUID | None
    case_version: int
    evidence_revision: int
    access_revision: int
    validation_status: Literal["stored_not_revalidated"] = "stored_not_revalidated"


class InvestigationHistory(Contract):
    items: list[InvestigationHistoryItem] = Field(max_length=20)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=1000)


class PacketVerification(Contract):
    verifier: Literal["trueflag.source-packet-verifier.v1"]
    status: Literal["source_numeric_reference_checks_passed"]
    record_count: int = Field(ge=0, le=200)
    transaction_count: int = Field(ge=0, le=200)
    financial_facts: int = Field(ge=0, le=8)
    manifest_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    packet_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    calculation_version: Literal["trueflag.transaction-analytics.v1"]
    human_semantic_review_required: Literal[True]
    legal_or_criminal_conclusion_validated: Literal[False]


class InvestigationDetail(InvestigationStatus):
    packet: InvestigationPacketBody | None = None
    verification: PacketVerification | None = None
