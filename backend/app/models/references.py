"""Versioned regulatory reference storage, separate from case observations/model policies."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base, Identity


class ReferenceSource(Identity, Base):
    __tablename__ = "reference_sources"
    key: Mapped[str] = mapped_column(String(80), unique=True)
    publisher: Mapped[str] = mapped_column(String(160))
    host: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class ReferenceDocument(Identity, Base):
    __tablename__ = "reference_documents"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("reference_sources.id"))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(600))
    authority: Mapped[str] = mapped_column(String(40))
    jurisdiction: Mapped[str] = mapped_column(String(16))
    entity: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(8))
    origin: Mapped[str] = mapped_column(String(24))
    __table_args__ = (
        UniqueConstraint("id", "source_id", name="uq_ref_document_source"),
        CheckConstraint(
            "authority IN ('binding_regulation','statute','guidance','internal_policy')",
            name="ck_ref_authority",
        ),
        CheckConstraint("origin IN ('official_curated','synthetic_test')", name="ck_ref_origin"),
    )


class ReferenceVersion(Identity, Base):
    __tablename__ = "reference_versions"
    document_id: Mapped[UUID] = mapped_column(ForeignKey("reference_documents.id"))
    version: Mapped[int] = mapped_column(Integer)
    raw: Mapped[bytes] = mapped_column(LargeBinary)
    raw_sha256: Mapped[str] = mapped_column(String(64))
    sections: Mapped[list] = mapped_column(JSON)
    extracted: Mapped[str] = mapped_column(Text)
    extracted_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(80))
    media_type: Mapped[str] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    publication_date: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    verified_through: Mapped[date | None] = mapped_column(Date)
    temporal_basis: Mapped[str] = mapped_column(String(32))
    snapshot_date: Mapped[date | None] = mapped_column(Date)
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid)
    admitted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        CheckConstraint("length(raw)>0 AND length(raw)<=1048576", name="ck_ref_raw_size"),
        CheckConstraint(
            "temporal_basis IN ('reviewed_interval','official_dated_snapshot','unknown')",
            name="ck_ref_temporal_basis",
        ),
        UniqueConstraint("id", "document_id", name="uq_ref_version_document"),
        UniqueConstraint("document_id", "version", name="uq_ref_document_version"),
        UniqueConstraint("document_id", "manifest_sha256", name="uq_ref_version_manifest"),
        ForeignKeyConstraint(
            ["supersedes_id", "document_id"],
            ["reference_versions.id", "reference_versions.document_id"],
            name="fk_ref_supersession_scope",
        ),
        CheckConstraint("version>=1 AND version<=100", name="ck_ref_version"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NOT NULL AND effective_to>effective_from",
            name="ck_ref_effective_interval",
        ),
        CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id!=id", name="ck_ref_no_self_supersession"
        ),
    )


class ReferenceChunk(Identity, Base):
    __tablename__ = "reference_chunks"
    version_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    section: Mapped[str] = mapped_column(String(120))
    locator: Mapped[str] = mapped_column(String(240))
    start_byte: Mapped[int] = mapped_column(Integer)
    end_byte: Mapped[int] = mapped_column(Integer)
    body_text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint(
            "length(body_text)>0 AND length(body_text)<=32768", name="ck_ref_chunk_size"
        ),
        ForeignKeyConstraint(
            ["version_id", "document_id"],
            ["reference_versions.id", "reference_versions.document_id"],
            name="fk_ref_chunk_version",
        ),
        UniqueConstraint("version_id", "section", name="uq_ref_chunk_section"),
        CheckConstraint("start_byte>=0 AND end_byte>start_byte", name="ck_ref_locator"),
    )


class ReferenceApproval(Identity, Base):
    __tablename__ = "reference_approvals"
    version_id: Mapped[UUID] = mapped_column(ForeignKey("reference_versions.id"), unique=True)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    review_kind: Mapped[str] = mapped_column(String(24))
    attestation: Mapped[str] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("review_kind IN ('human','test_fixture')", name="ck_ref_review_kind"),
    )


class CorpusRelease(Identity, Base):
    __tablename__ = "corpus_releases"
    manifest_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    published_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    review_kind: Mapped[str] = mapped_column(String(24))
    index_version: Mapped[str] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("review_kind IN ('human','test_fixture')", name="ck_corpus_review_kind"),
    )


class CorpusMember(Base):
    __tablename__ = "corpus_members"
    release_id: Mapped[UUID] = mapped_column(ForeignKey("corpus_releases.id"), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "document_id"],
            ["reference_versions.id", "reference_versions.document_id"],
            name="fk_corpus_member_document",
        ),
        UniqueConstraint("release_id", "document_id", name="uq_corpus_release_document"),
    )


class ReferenceContext(Identity, Base):
    __tablename__ = "reference_contexts"
    release_id: Mapped[UUID] = mapped_column(ForeignKey("corpus_releases.id"))
    jurisdiction: Mapped[str] = mapped_column(String(16))
    entity: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(8))
    as_of: Mapped[date] = mapped_column(Date)
    knowledge_cutoff: Mapped[date] = mapped_column(Date)
    approved_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "jurisdiction",
            "entity",
            "language",
            "as_of",
            "knowledge_cutoff",
            name="uq_reference_context",
        ),
    )


class ReferenceGrant(Base):
    __tablename__ = "reference_grants"
    context_id: Mapped[UUID] = mapped_column(ForeignKey("reference_contexts.id"), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean)
    revision: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (CheckConstraint("revision>=1", name="ck_reference_grant_revision"),)


class ReferenceEvent(Identity, Base):
    __tablename__ = "reference_events"
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("reference_sources.id"))
    version_id: Mapped[UUID | None] = mapped_column(ForeignKey("reference_versions.id"))
    release_id: Mapped[UUID | None] = mapped_column(ForeignKey("corpus_releases.id"))
    action: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        CheckConstraint("action='withdraw'", name="ck_reference_event_action"),
        CheckConstraint(
            "(CASE WHEN source_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN version_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN release_id IS NOT NULL THEN 1 ELSE 0 END)=1",
            name="ck_reference_event_target",
        ),
    )


REFERENCE_TABLES = tuple(
    c.__table__
    for c in (
        ReferenceSource,
        ReferenceDocument,
        ReferenceVersion,
        ReferenceChunk,
        ReferenceApproval,
        CorpusRelease,
        CorpusMember,
        ReferenceContext,
        ReferenceGrant,
        ReferenceEvent,
    )
)

# Expression index; SQLite compatibility migrations deliberately omit PostgreSQL full-text indexing.
Index(
    "ix_reference_chunks_fts",
    text("to_tsvector('english'::regconfig, body_text)"),
    _table=ReferenceChunk.__table__,
    postgresql_using="gin",
)
