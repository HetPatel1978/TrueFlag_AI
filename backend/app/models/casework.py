"""Append-only human casework, separate from immutable model recommendations."""

from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base, Identity


class CaseworkEntry(Identity, Base):
    __tablename__ = "casework_entries"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    author: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(32))
    parent_id: Mapped[UUID | None] = mapped_column(Uuid)
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    binding: Mapped[dict] = mapped_column(JSON)
    audit_event_id: Mapped[UUID] = mapped_column(ForeignKey("audit_events.id"), unique=True)
    __table_args__ = (
        UniqueConstraint("case_id", "revision", name="uq_casework_revision"),
        UniqueConstraint("actor_id", "key_sha256", name="uq_casework_idempotency"),
        UniqueConstraint("case_id", "id", name="uq_casework_parent_scope"),
        ForeignKeyConstraint(
            ["case_id", "parent_id"],
            ["casework_entries.case_id", "casework_entries.id"],
            name="fk_casework_parent",
        ),
        CheckConstraint("revision BETWEEN 1 AND 1000", name="ck_casework_revision"),
        CheckConstraint(
            "kind IN ('note','information_request','information_response','finding_review','escalation','supervisor_response','resolution')",
            name="ck_casework_kind",
        ),
        CheckConstraint(
            "length(CAST(payload AS TEXT)) <= 12288 AND length(CAST(binding AS TEXT)) <= 8192",
            name="ck_casework_bounds",
        ),
    )
