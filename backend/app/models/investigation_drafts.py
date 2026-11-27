"""Immutable draft provenance/usage with a small child queue for existing investigation runs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base, Identity


class DraftRun(Identity, Base):
    __tablename__ = "investigation_draft_runs"
    parent_run_id: Mapped[UUID] = mapped_column(Uuid)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    parent_manifest_sha256: Mapped[str] = mapped_column(String(64))
    config_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    configuration: Mapped[dict] = mapped_column(JSON)
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["parent_run_id", "actor_id", "parent_manifest_sha256"],
            [
                "investigation_runs.id",
                "investigation_runs.actor_id",
                "investigation_runs.manifest_sha256",
            ],
            name="fk_draft_parent_scope",
        ),
        UniqueConstraint("parent_run_id", "config_sha256", name="uq_draft_intent"),
        UniqueConstraint("id", "actor_id", "manifest_sha256", name="uq_draft_request_scope"),
        UniqueConstraint("id", "manifest_sha256", name="uq_draft_result_scope"),
        CheckConstraint("length(CAST(configuration AS TEXT))<=4096", name="ck_draft_config_size"),
    )


class DraftRequest(Base):
    __tablename__ = "investigation_draft_requests"
    actor_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "actor_id", "manifest_sha256"],
            [
                "investigation_draft_runs.id",
                "investigation_draft_runs.actor_id",
                "investigation_draft_runs.manifest_sha256",
            ],
            name="fk_draft_request_scope",
        ),
    )


class DraftJob(Base):
    __tablename__ = "investigation_draft_jobs"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigation_draft_runs.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[UUID | None] = mapped_column(ForeignKey("investigation_workers.id"))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','abstained','failed','invalidated') AND attempts BETWEEN 0 AND 3",
            name="ck_draft_job_state",
        ),
        CheckConstraint(
            "(status='running' AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND deadline IS NOT NULL AND attempts>0) OR (status!='running' AND worker_id IS NULL AND lease_token IS NULL AND lease_until IS NULL AND deadline IS NULL)",
            name="ck_draft_job_lease",
        ),
        Index("ix_draft_job_claim", "status", "not_before"),
    )


class DraftAttempt(Identity, Base):
    __tablename__ = "investigation_draft_attempts"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("investigation_draft_runs.id"))
    attempt: Mapped[int] = mapped_column(Integer)
    lease_sha256: Mapped[str] = mapped_column(String(64))
    packet_sha256: Mapped[str] = mapped_column(String(64))
    minimized_sha256: Mapped[str] = mapped_column(String(64))
    input_reservation: Mapped[int] = mapped_column(Integer)
    output_reservation: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("run_id", "attempt", name="uq_draft_attempt"),
        UniqueConstraint("id", "run_id", name="uq_draft_attempt_scope"),
        CheckConstraint(
            "attempt BETWEEN 1 AND 3 AND input_reservation BETWEEN 1 AND 65536 AND output_reservation BETWEEN 256 AND 16384",
            name="ck_draft_attempt_budget",
        ),
    )


class DraftReceipt(Identity, Base):
    __tablename__ = "investigation_draft_receipts"
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigation_draft_attempts.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(40))
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[dict | None] = mapped_column(JSON)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed','provider_timeout','provider_unavailable','provider_incomplete','provider_refused','invalid_provider_output','verification_failed','budget_exhausted','authorization_revoked','input_invalidated','worker_revoked','lease_expired','database_unavailable')",
            name="ck_draft_receipt_status",
        ),
        CheckConstraint(
            "elapsed_ms IS NULL OR elapsed_ms BETWEEN 0 AND 60000", name="ck_draft_elapsed"
        ),
    )


class StoredDraft(Identity, Base):
    __tablename__ = "investigation_drafts"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("investigation_draft_runs.id"), unique=True)
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigation_draft_attempts.id"), unique=True
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "run_id"],
            ["investigation_draft_attempts.id", "investigation_draft_attempts.run_id"],
            name="fk_draft_result_attempt",
        ),
        ForeignKeyConstraint(
            ["run_id", "manifest_sha256"],
            ["investigation_draft_runs.id", "investigation_draft_runs.manifest_sha256"],
            name="fk_draft_result_manifest",
        ),
        CheckConstraint("length(CAST(body AS TEXT))<=524288", name="ck_draft_body_size"),
    )


DRAFT_TABLES = tuple(
    c.__table__ for c in (DraftRun, DraftRequest, DraftJob, DraftAttempt, DraftReceipt, StoredDraft)
)
