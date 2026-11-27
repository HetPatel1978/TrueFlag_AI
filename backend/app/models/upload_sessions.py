"""Persistent workspace selection; canonical cases and scientific records stay unchanged."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base, Identity


class UploadSession(Identity, Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (UniqueConstraint("actor_id", "key_sha256", name="uq_upload_session_key"),)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    key_sha256: Mapped[str] = mapped_column(String(64))
    creation_version: Mapped[int] = mapped_column(default=0)


class UploadSessionItem(Base):
    __tablename__ = "upload_session_items"
    upload_id: Mapped[UUID] = mapped_column(ForeignKey("csv_uploads.id"), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("upload_sessions.id"), index=True)


class UploadWorkspace(Base):
    __tablename__ = "upload_workspaces"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_upload_workspace_version"),)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("upload_sessions.id"))
    version: Mapped[int] = mapped_column(default=1)
