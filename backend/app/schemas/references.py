"""Reference curation and read contracts; never model tools or customer conclusions."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.assessments import SHA256

PARSER_VERSION = "trueflag.reference-parser.v1"
INDEX_VERSION = "trueflag.pg-english-reference.v1"
AS_OF = date(2026, 11, 2)  # Explicit user-authorized historical development boundary.
KNOWLEDGE_CUTOFF = date(2026, 11, 4)
Authority = Literal["binding_regulation", "statute", "guidance", "internal_policy"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class DocumentSpec(Contract):
    key: str = Field(pattern=r"^[a-z][a-z0-9-]{2,79}$")
    title: str = Field(min_length=3, max_length=300)
    url: str = Field(min_length=12, max_length=600)
    authority: Authority
    jurisdiction: str = Field(default="US", min_length=2, max_length=16)
    entity: str = Field(default="us_bank", min_length=2, max_length=40)
    language: str = Field(default="en", min_length=2, max_length=8)
    origin: Literal["official_curated", "synthetic_test"] = "official_curated"


class VersionSpec(Contract):
    media_type: Literal["application/xml", "text/html", "text/plain"]
    raw_sha256: SHA256
    sections: tuple[str, ...] = Field(min_length=1, max_length=100)
    retrieved_at: datetime
    publication_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    verified_through: date | None = None
    temporal_basis: Literal["reviewed_interval", "official_dated_snapshot", "unknown"] = "unknown"
    snapshot_date: date | None = None

    @field_validator("retrieved_at")
    @classmethod
    def canonical_timestamp(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Aware retrieval timestamp required")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def explicit_dates(self):
        if self.effective_to is not None and (
            self.effective_from is None or self.effective_to <= self.effective_from
        ):
            raise ValueError("Invalid effective interval")
        if self.temporal_basis == "official_dated_snapshot" and self.snapshot_date is None:
            raise ValueError("Dated snapshot identity required")
        return self


class Approval(Contract):
    manifest_sha256: SHA256
    approve: Literal[True]
    review_kind: Literal["human", "test_fixture"]
    attestation: Literal["reviewed_provenance_rights_dates_full_sections_and_exceptions"]
    review_reference_sha256: SHA256 | None = None


class ReferenceQuery(Contract):
    query: str | None = Field(default=None, min_length=1, max_length=256)
    section: str | None = Field(default=None, min_length=1, max_length=120)
    limit: int = Field(default=5, strict=True, ge=1, le=5)

    @model_validator(mode="after")
    def bounded_operation(self):
        if (self.query is None) == (self.section is None):
            raise ValueError("Exactly one search phrase or section is required")
        value = self.query if self.query is not None else self.section
        if not value.strip() or len(value.split()) > 40 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid reference search")
        return self


class Citation(Contract):
    reference_id: UUID
    context_id: UUID
    release_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_id: UUID
    publisher: str
    title: str
    authority: Authority
    origin: Literal["official_curated", "synthetic_test"]
    source_url: str
    section: str
    locator: str
    start_byte: int
    end_byte: int
    text: str = Field(max_length=32768)
    text_sha256: SHA256
    raw_sha256: SHA256
    extracted_sha256: SHA256
    parser_version: str
    publication_date: date | None
    effective_from: date | None
    effective_to: date | None
    snapshot_date: date | None
    temporal_basis: str
    verified_through: date | None
    retrieved_at: datetime
    as_of: date
    jurisdiction: str
    entity: str
    language: str
    applicability: Literal["potentially_applicable_context_human_review_required"] = (
        "potentially_applicable_context_human_review_required"
    )
    is_customer_violation_evidence: Literal[False] = False
    limitations: list[str] = Field(max_length=12)


class ReferenceResult(Contract):
    schema_version: Literal["trueflag.reference-result.v1"] = "trueflag.reference-result.v1"
    status: Literal[
        "available", "empty", "ambiguous", "unavailable", "outdated", "withdrawn", "inapplicable"
    ]
    context_id: UUID | None
    release_id: UUID | None
    release_sha256: SHA256 | None = None
    as_of: date = AS_OF
    jurisdiction: Literal["US"] = "US"
    entity: Literal["us_bank"] = "us_bank"
    language: Literal["en"] = "en"
    index_version: Literal["trueflag.pg-english-reference.v1"] = INDEX_VERSION
    passages: list[Citation] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(max_length=12)
