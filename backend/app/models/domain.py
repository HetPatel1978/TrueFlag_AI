from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
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
    __table_args__ = (
        CheckConstraint("role IN ('analyst','supervisor','admin')", name="ck_user_role"),
    )
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


class CSVUpload(Identity, Base):
    """Private staging receipt only; no canonical alerts or ML jobs are created."""

    __tablename__ = "csv_uploads"
    __table_args__ = (
        UniqueConstraint("actor_id", "key_sha256", name="uq_csv_actor_key"),
        CheckConstraint("status IN ('staged','expired')", name="ck_csv_status"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 8388608", name="ck_csv_size"),
        CheckConstraint("row_count > 0 AND row_count <= 10000", name="ck_csv_rows"),
        CheckConstraint("column_count > 0 AND column_count <= 128", name="ck_csv_columns"),
        CheckConstraint("expires_at > created_at", name="ck_csv_expiry"),
        Index("ix_csv_actor_status_expiry", "actor_id", "status", "expires_at"),
        Index("ix_csv_status_expiry", "status", "expires_at"),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="staged")
    size_bytes: Mapped[int] = mapped_column()
    row_count: Mapped[int] = mapped_column()
    column_count: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    key_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(40), unique=True)
    csv_contract_version: Mapped[str] = mapped_column(String(60))
    feature_contract_version: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    audit_event_id: Mapped[UUID] = mapped_column(ForeignKey("audit_events.id"), unique=True)


class CSVValidation(Identity, Base):
    __tablename__ = "csv_validations"
    __table_args__ = (
        UniqueConstraint("upload_id", "mapping_sha256", name="uq_csv_validation_mapping"),
        UniqueConstraint("upload_id", "version", name="uq_csv_validation_version"),
        CheckConstraint(
            "version >= 1 AND total_rows > 0 AND total_rows <= 10000",
            name="ck_csv_validation_version",
        ),
        CheckConstraint(
            "valid_rows >= 0 AND invalid_rows >= 0 AND valid_rows + invalid_rows = total_rows AND warning_rows >= 0 AND warning_rows <= total_rows",
            name="ck_csv_validation_counts",
        ),
    )
    upload_id: Mapped[UUID] = mapped_column(ForeignKey("csv_uploads.id"))
    version: Mapped[int] = mapped_column()
    mapping_sha256: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[dict] = mapped_column(JSON)
    mapping_version: Mapped[str] = mapped_column(String(60))
    validator_version: Mapped[str] = mapped_column(String(60))
    units: Mapped[str] = mapped_column(String(40))
    upload_sha256: Mapped[str] = mapped_column(String(64))
    feature_contract_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column()
    valid_rows: Mapped[int] = mapped_column()
    invalid_rows: Mapped[int] = mapped_column()
    warning_rows: Mapped[int] = mapped_column()
    audit_event_id: Mapped[UUID] = mapped_column(ForeignKey("audit_events.id"), unique=True)


class CSVValidationIssue(Base):
    __tablename__ = "csv_validation_issues"
    validation_id: Mapped[UUID] = mapped_column(ForeignKey("csv_validations.id"), primary_key=True)
    row_number: Mapped[int] = mapped_column(primary_key=True)
    invalid: Mapped[bool] = mapped_column(Boolean)
    has_warnings: Mapped[bool] = mapped_column(Boolean)
    errors: Mapped[list] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("row_number >= 2 AND row_number <= 10001", name="ck_csv_issue_row"),
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
        CheckConstraint("version >= 1", name="ck_case_version"),
        Index("ix_cases_assigned_created_id", "assigned_to", "created_at", "id"),
        Index("ix_cases_status_created_id", "status", "created_at", "id"),
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
    route: Mapped[str | None] = mapped_column(String(40))
    processing_status: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        CheckConstraint("mode IN ('Efficiency','Balanced','Coverage')", name="ck_decision_mode"),
        CheckConstraint(
            "(processing_status = 'processed' AND route IS NOT NULL AND "
            "route IN ('retain','dismiss','retain_human_review','review_reduction_candidate')) OR "
            "(processing_status = 'failed' AND route IS NULL)",
            name="ck_decision_route",
        ),
    )


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AlertIngestion(Identity, Base):
    """Durable creation receipt; store a hash rather than the raw request key."""

    __tablename__ = "alert_ingestions"
    __table_args__ = (UniqueConstraint("key_sha256", name="uq_alert_ingestions_key"),)
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    response_json: Mapped[dict] = mapped_column(JSON)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    __table_args__ = (CheckConstraint("attempt_count >= 1", name="ck_login_attempt_count"),)
    key_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column()


class AssessmentAPIThrottle(Base):
    __tablename__ = "assessment_api_throttles"
    __table_args__ = (CheckConstraint("request_count >= 1", name="ck_assessment_api_count"),)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column()


class OperationalMetric(Base):
    """Replaceable cumulative minute snapshots; contains no business identifiers."""

    __tablename__ = "operational_metrics"
    __table_args__ = (
        CheckConstraint("count >= 0 AND total_ms >= 0", name="ck_metric_values"),
        Index("ix_operational_metrics_minute", "minute"),
    )
    instance_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    minute: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column()
    total_ms: Mapped[float] = mapped_column(Float)
    buckets: Mapped[list] = mapped_column(JSON)


class AssessmentExplanation(Identity, Base):
    """Immutable verified explanation; no raw feature values are copied."""

    __tablename__ = "assessment_explanations"
    payload: Mapped[dict] = mapped_column(JSON)
    verification: Mapped[dict] = mapped_column(JSON)


class Assessment(Identity, Base):
    """Append-only completed run linking existing score, recommendation and audit records."""

    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_assessment_case_version"),
        UniqueConstraint("run_id", name="uq_assessment_run"),
        UniqueConstraint("key_sha256", name="uq_assessment_key"),
        CheckConstraint("version >= 1 AND case_version >= 1", name="ck_assessment_version"),
        CheckConstraint("status = 'completed'", name="ck_assessment_completed"),
    )
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column()
    case_version: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="completed")
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    input_sha256: Mapped[str] = mapped_column(String(64))
    score_id: Mapped[UUID] = mapped_column(ForeignKey("model_scores.id"), unique=True)
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("decisions.id"), unique=True)
    explanation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assessment_explanations.id"), unique=True
    )
    audit_event_id: Mapped[UUID] = mapped_column(ForeignKey("audit_events.id"), unique=True)
    provenance: Mapped[dict] = mapped_column(JSON)


class AssessmentWorker(Identity, Base):
    """Dedicated non-login service identity; its only permission is assessment execution."""

    __tablename__ = "assessment_workers"
    name: Mapped[str] = mapped_column(String(64), unique=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    provisioned_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class AssessmentJob(Identity, Base):
    __tablename__ = "assessment_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_job_run"),
        UniqueConstraint("key_sha256", name="uq_job_key"),
        CheckConstraint("policy IN ('Efficiency','Balanced','Coverage')", name="ck_job_policy"),
        CheckConstraint("expected_version >= 1", name="ck_job_version"),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="ck_job_attempts"),
        CheckConstraint(
            "(status = 'pending' AND assessment_id IS NULL AND lease_token IS NULL AND "
            "lease_until IS NULL AND deadline IS NULL AND fallback_route IS NULL) OR "
            "(status = 'running' AND assessment_id IS NULL AND lease_token IS NOT NULL AND "
            "lease_until IS NOT NULL AND deadline IS NOT NULL AND worker_id IS NOT NULL AND "
            "attempts >= 1 AND fallback_route IS NULL) OR "
            "(status = 'succeeded' AND assessment_id IS NOT NULL AND lease_token IS NULL AND "
            "lease_until IS NULL AND deadline IS NULL AND fallback_route IS NULL) OR "
            "(status = 'failed' AND assessment_id IS NULL AND lease_token IS NULL AND "
            "lease_until IS NULL AND deadline IS NULL AND fallback_route IS NOT NULL AND "
            "fallback_route = 'manual_review' "
            "AND failure_code IS NOT NULL)",
            name="ck_job_state",
        ),
        Index("ix_job_ready", "status", "available_at", "id"),
        Index("ix_job_expiry", "status", "lease_until"),
    )
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[UUID] = mapped_column(Uuid)
    expected_version: Mapped[int] = mapped_column()
    policy: Mapped[str] = mapped_column(String(20))
    key_sha256: Mapped[str] = mapped_column(String(64))
    request_sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    worker_id: Mapped[UUID | None] = mapped_column(ForeignKey("assessment_workers.id"))
    assessment_id: Mapped[UUID | None] = mapped_column(ForeignKey("assessments.id"), unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    fallback_route: Mapped[str | None] = mapped_column(String(20))
