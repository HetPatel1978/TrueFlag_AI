"""Additive synthetic evidence foundation; legacy Evidence and scientific records unchanged."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.domain import Base, Identity, utcnow

KINDS = "'customer','account','relationship','transaction'"


class EvidenceSource(Identity, Base):
    __tablename__ = "evidence_sources"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    scenario_id: Mapped[UUID] = mapped_column(Uuid)
    classification: Mapped[str] = mapped_column(String(20), default="synthetic")
    __table_args__ = (
        UniqueConstraint("owner_id", "scenario_id", name="uq_ev_source_owner_scenario"),
        CheckConstraint("classification='synthetic'", name="ck_ev_synthetic"),
    )


class EvidenceSourceVersion(Identity, Base):
    __tablename__ = "evidence_source_versions"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_sources.id"))
    version: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON)
    configuration: Mapped[dict] = mapped_column(JSON)
    declarations: Mapped[dict] = mapped_column(JSON)
    reconciliation: Mapped[dict] = mapped_column(JSON)
    coverage: Mapped[str] = mapped_column(String(32))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    admitted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("source_id", "version", name="uq_ev_source_version"),
        UniqueConstraint("source_id", "content_sha256", name="uq_ev_source_digest"),
        UniqueConstraint("id", "source_id", name="uq_ev_release_scope"),
        CheckConstraint(
            "version>=1 AND version<=100 AND window_start<as_of", name="ck_ev_release_time"
        ),
        CheckConstraint(
            "coverage IN ('complete_declared_window','partial','unavailable')",
            name="ck_ev_coverage",
        ),
    )


class EvidenceIdentity(Identity, Base):
    __tablename__ = "evidence_identities"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_sources.id"))
    record_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("source_id", "record_key", name="uq_ev_record_key"),
        UniqueConstraint("id", "source_id", "kind", name="uq_ev_identity_scope"),
        CheckConstraint(f"kind IN ({KINDS})", name="ck_ev_identity_kind"),
    )


class EvidenceRecordVersion(Identity, Base):
    __tablename__ = "evidence_record_versions"
    source_id: Mapped[UUID] = mapped_column(Uuid)
    source_version_id: Mapped[UUID] = mapped_column(Uuid)
    identity_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid)
    __table_args__ = (
        UniqueConstraint("identity_id", "version", name="uq_ev_record_version"),
        UniqueConstraint("source_version_id", "identity_id", name="uq_ev_release_record"),
        UniqueConstraint("id", "source_id", "kind", name="uq_ev_payload_scope"),
        UniqueConstraint("id", "source_id", "identity_id", name="uq_ev_correction_scope"),
        ForeignKeyConstraint(
            ["source_version_id", "source_id"],
            ["evidence_source_versions.id", "evidence_source_versions.source_id"],
            name="fk_ev_release_scope",
        ),
        ForeignKeyConstraint(
            ["identity_id", "source_id", "kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_identity_scope",
        ),
        ForeignKeyConstraint(
            ["supersedes_id", "source_id", "identity_id"],
            [
                "evidence_record_versions.id",
                "evidence_record_versions.source_id",
                "evidence_record_versions.identity_id",
            ],
            name="fk_ev_correction_scope",
        ),
        CheckConstraint(f"kind IN ({KINDS}) AND version>=1", name="ck_ev_record_kind"),
        CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id!=id", name="ck_ev_no_self_correction"
        ),
    )


def typed_args(kind):
    return (
        ForeignKeyConstraint(
            ["record_version_id", "source_id", "kind"],
            [
                "evidence_record_versions.id",
                "evidence_record_versions.source_id",
                "evidence_record_versions.kind",
            ],
            name="fk_ev_" + kind + "_payload",
        ),
        CheckConstraint(f"kind='{kind}'", name="ck_ev_" + kind + "_payload"),
    )


class EvidenceCustomer(Base):
    __tablename__ = "evidence_customers"
    record_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20), default="customer")
    subject_key: Mapped[str] = mapped_column(String(80))
    alias: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    annual_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(3))
    kyc_score: Mapped[int] = mapped_column(Integer)
    __table_args__ = typed_args("customer") + (
        CheckConstraint(
            "(annual_income IS NULL OR annual_income>=0 AND annual_income<10000000000000000) AND kyc_score BETWEEN 0 AND 6 AND currency IN ('USD','CAD','EUR','GBP')",
            name="ck_ev_customer_values",
        ),
    )


class EvidenceAccount(Base):
    __tablename__ = "evidence_accounts"
    record_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20), default="account")
    alias: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = typed_args("account") + (
        CheckConstraint("currency IN ('USD','CAD','EUR','GBP')", name="ck_ev_account_currency"),
    )


class EvidenceRelationship(Base):
    __tablename__ = "evidence_relationships"
    record_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20), default="relationship")
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    customer_kind: Mapped[str] = mapped_column(String(20), default="customer")
    account_id: Mapped[UUID] = mapped_column(Uuid)
    account_kind: Mapped[str] = mapped_column(String(20), default="account")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    relation: Mapped[str] = mapped_column(String(32), default="declared_holder")
    __table_args__ = typed_args("relationship") + (
        ForeignKeyConstraint(
            ["customer_id", "source_id", "customer_kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_holder_customer",
        ),
        ForeignKeyConstraint(
            ["account_id", "source_id", "account_kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_holder_account",
        ),
        CheckConstraint(
            "customer_kind='customer' AND account_kind='account' AND relation='declared_holder'",
            name="ck_ev_holder_kind",
        ),
    )


class EvidenceTransaction(Base):
    __tablename__ = "evidence_transactions"
    record_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20), default="transaction")
    account_id: Mapped[UUID] = mapped_column(Uuid)
    counterparty_id: Mapped[UUID | None] = mapped_column(Uuid)
    account_kind: Mapped[str] = mapped_column(String(20), default="account")
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(3))
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_time: Mapped[str] = mapped_column(String(64))
    event_kind: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(10))
    channel: Mapped[str] = mapped_column(String(16))
    reverses_id: Mapped[UUID | None] = mapped_column(Uuid)
    reverse_kind: Mapped[str] = mapped_column(String(20), default="transaction")
    __table_args__ = typed_args("transaction") + (
        ForeignKeyConstraint(
            ["account_id", "source_id", "account_kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_tx_account",
        ),
        ForeignKeyConstraint(
            ["counterparty_id", "source_id", "account_kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_tx_counterparty",
        ),
        ForeignKeyConstraint(
            ["reverses_id", "source_id", "reverse_kind"],
            ["evidence_identities.id", "evidence_identities.source_id", "evidence_identities.kind"],
            name="fk_ev_tx_reversal",
        ),
        CheckConstraint(
            "account_kind='account' AND reverse_kind='transaction' AND amount>=0 AND amount<10000000000000000 AND currency IN ('USD','CAD','EUR','GBP')",
            name="ck_ev_tx_amount",
        ),
        CheckConstraint(
            "event_kind IN ('purchase','payment','transfer','merchant_credit','customer_refund','reversal') AND direction IN ('debit','credit') AND channel IN ('card','cashlike','internal')",
            name="ck_ev_tx_codes",
        ),
        CheckConstraint(
            "(event_kind='reversal')=(reverses_id IS NOT NULL)", name="ck_ev_tx_reversal"
        ),
    )


class CaseEvidenceState(Base):
    __tablename__ = "case_evidence_states"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    evidence_revision: Mapped[int] = mapped_column(Integer, default=0)
    access_revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        CheckConstraint("evidence_revision>=0 AND access_revision>=0", name="ck_ev_revisions"),
    )


class EvidenceCaseBinding(Base):
    __tablename__ = "evidence_case_bindings"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_sources.id"), unique=True)
    source_version_id: Mapped[UUID] = mapped_column(Uuid)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    input_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("case_id", "source_id", name="uq_ev_binding_scope"),
        ForeignKeyConstraint(
            ["source_version_id", "source_id"],
            ["evidence_source_versions.id", "evidence_source_versions.source_id"],
            name="fk_ev_binding_release",
        ),
    )


class EvidenceSourceAccess(Base):
    __tablename__ = "evidence_source_access"
    case_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "source_id"],
            ["evidence_case_bindings.case_id", "evidence_case_bindings.source_id"],
            name="fk_ev_access_binding",
        ),
    )


class CaseEvidenceLink(Base):
    __tablename__ = "case_evidence_links"
    case_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    record_version_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "source_id"],
            ["evidence_case_bindings.case_id", "evidence_case_bindings.source_id"],
            name="fk_ev_link_binding",
        ),
        ForeignKeyConstraint(
            ["record_version_id", "source_id", "kind"],
            [
                "evidence_record_versions.id",
                "evidence_record_versions.source_id",
                "evidence_record_versions.kind",
            ],
            name="fk_ev_link_record",
        ),
    )


EVIDENCE_TABLES = tuple(
    c.__table__
    for c in (
        EvidenceSource,
        EvidenceSourceVersion,
        EvidenceIdentity,
        EvidenceRecordVersion,
        EvidenceCustomer,
        EvidenceAccount,
        EvidenceRelationship,
        EvidenceTransaction,
        CaseEvidenceState,
        EvidenceCaseBinding,
        EvidenceSourceAccess,
        CaseEvidenceLink,
    )
)
