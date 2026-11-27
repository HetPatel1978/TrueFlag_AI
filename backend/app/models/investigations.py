"""Evidence-only immutable inputs/results and a separate fenced PostgreSQL queue."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
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


class InvestigationWorker(Identity, Base):
    __tablename__ = "investigation_workers"
    name: Mapped[str] = mapped_column(String(64), unique=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    provisioned_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class InvestigationRun(Identity, Base):
    __tablename__ = "investigation_runs"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"))
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"))
    assessment_id: Mapped[UUID | None] = mapped_column(ForeignKey("assessments.id"))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    input_manifest: Mapped[dict] = mapped_column(JSON)
    coordinator_version: Mapped[str] = mapped_column(String(80))
    __table_args__ = (
        UniqueConstraint("actor_id", "case_id", "manifest_sha256", name="uq_inv_intent"),
        UniqueConstraint("id", "actor_id", "manifest_sha256", name="uq_inv_request_scope"),
        UniqueConstraint("id", "manifest_sha256", name="uq_inv_packet_scope"),
        CheckConstraint(
            "length(CAST(input_manifest AS TEXT))<=131072", name="ck_inv_manifest_size"
        ),
    )


class InvestigationRequestKey(Base):
    __tablename__ = "investigation_requests"
    actor_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "actor_id", "manifest_sha256"],
            [
                "investigation_runs.id",
                "investigation_runs.actor_id",
                "investigation_runs.manifest_sha256",
            ],
            name="fk_inv_request_scope",
        ),
    )


class InvestigationJob(Base):
    __tablename__ = "investigation_jobs"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("investigation_runs.id"), primary_key=True)
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
            name="ck_inv_job_state",
        ),
        CheckConstraint(
            "(status='running' AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND deadline IS NOT NULL AND attempts>0) OR (status!='running' AND worker_id IS NULL AND lease_token IS NULL AND lease_until IS NULL AND deadline IS NULL)",
            name="ck_inv_job_lease",
        ),
        Index("ix_inv_job_claim", "status", "not_before"),
    )


class InvestigationPacket(Identity, Base):
    __tablename__ = "investigation_packets"
    run_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    verification: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "manifest_sha256"],
            ["investigation_runs.id", "investigation_runs.manifest_sha256"],
            name="fk_inv_packet_scope",
        ),
        CheckConstraint("length(CAST(body AS TEXT))<=524288", name="ck_inv_packet_size"),
    )


INVESTIGATION_TABLES = tuple(
    c.__table__
    for c in (
        InvestigationWorker,
        InvestigationRun,
        InvestigationRequestKey,
        InvestigationJob,
        InvestigationPacket,
    )
)
