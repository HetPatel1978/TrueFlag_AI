from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Identity, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('analyst','admin')", name="ck_user_role"),)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(Identity, Base):
    __tablename__ = "alerts"
    source_id: Mapped[str] = mapped_column(String(128), unique=True)
    data_classification: Mapped[str] = mapped_column(String(30), default="synthetic")
    feature_contract_version: Mapped[str] = mapped_column(String(100))
    features: Mapped[dict] = mapped_column(JSON)
    input_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("data_classification = 'synthetic'", name="ck_alert_synthetic_only"),
    )


class Case(Identity, Base):
    __tablename__ = "cases"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), unique=True)
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="open")
    disposition: Mapped[str | None] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_review','awaiting_approval','closed')", name="ck_case_status"
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('close','recommend')", name="ck_disposition"
        ),
    )


class Evidence(Identity, Base):
    __tablename__ = "evidence"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    source_uri: Mapped[str] = mapped_column(String(2048))
    content_sha256: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(50))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelScore(Identity, Base):
    __tablename__ = "model_scores"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(100))
    model_sha256: Mapped[str] = mapped_column(String(64))
    input_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        CheckConstraint(
            "(status = 'processed' AND score IS NOT NULL AND score >= 0 AND score <= 1) OR "
            "(status = 'failed' AND score IS NULL)",
            name="ck_score_processing",
        ),
    )


class Decision(Identity, Base):
    __tablename__ = "decisions"
    score_id: Mapped[UUID] = mapped_column(ForeignKey("model_scores.id"), index=True)
    policy_version: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    route: Mapped[str | None] = mapped_column(String(20))
    processing_status: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        CheckConstraint("mode IN ('Efficiency','Balanced','Coverage')", name="ck_decision_mode"),
        CheckConstraint(
            "(processing_status = 'processed' AND route IS NOT NULL AND "
            "route IN ('retain','dismiss')) OR (processing_status = 'failed' AND route IS NULL)",
            name="ck_decision_route",
        ),
    )


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
