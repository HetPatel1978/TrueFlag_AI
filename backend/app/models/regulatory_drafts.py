"""Immutable regulatory context stored alongside the existing durable draft job."""

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base


class DraftRegulatoryBinding(Base):
    __tablename__ = "draft_regulatory_bindings"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigation_draft_runs.id"), primary_key=True
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"))
    parent_run_id: Mapped[UUID] = mapped_column(ForeignKey("investigation_runs.id"))
    run_manifest_sha256: Mapped[str] = mapped_column(String(64))
    binding_sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "actor_id", "run_manifest_sha256"],
            [
                "investigation_draft_runs.id",
                "investigation_draft_runs.actor_id",
                "investigation_draft_runs.manifest_sha256",
            ],
            name="fk_regulatory_draft_scope",
        ),
        CheckConstraint("length(CAST(body AS TEXT))<=65536", name="ck_regulatory_draft_size"),
    )
