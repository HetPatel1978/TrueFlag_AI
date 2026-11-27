"""Initial domain schema; no scientific data or default users."""

import sqlalchemy as sa

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "users",
        *identity(),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("role IN ('analyst','admin')", name="ck_user_role"),
    )
    op.create_table(
        "alerts",
        *identity(),
        sa.Column("source_id", sa.String(128), nullable=False, unique=True),
        sa.Column("data_classification", sa.String(30), nullable=False),
        sa.Column("feature_contract_version", sa.String(100), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("data_classification = 'synthetic'", name="ck_alert_synthetic_only"),
    )
    op.create_table(
        "cases",
        *identity(),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False, unique=True),
        sa.Column("assigned_to", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("disposition", sa.String(30)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','in_review','awaiting_approval','closed')", name="ck_case_status"
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('close','recommend')", name="ck_disposition"
        ),
    )
    op.create_table(
        "evidence",
        *identity(),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("source_uri", sa.String(2048), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(50), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_case_id", "evidence", ["case_id"])
    op.create_table(
        "model_scores",
        *identity(),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("model_sha256", sa.String(64), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("failure_code", sa.String(100)),
        sa.CheckConstraint(
            "(status = 'processed' AND score IS NOT NULL AND score >= 0 AND score <= 1) OR (status = 'failed' AND score IS NULL)",
            name="ck_score_processing",
        ),
    )
    op.create_index("ix_model_scores_alert_id", "model_scores", ["alert_id"])
    op.create_table(
        "decisions",
        *identity(),
        sa.Column("score_id", sa.Uuid(), sa.ForeignKey("model_scores.id"), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("route", sa.String(20)),
        sa.Column("processing_status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.CheckConstraint("mode IN ('Efficiency','Balanced','Coverage')", name="ck_decision_mode"),
        sa.CheckConstraint(
            "(processing_status = 'processed' AND route IS NOT NULL AND route IN ('retain','dismiss')) OR (processing_status = 'failed' AND route IS NULL)",
            name="ck_decision_route",
        ),
    )
    op.create_index("ix_decisions_score_id", "decisions", ["score_id"])
    op.create_table(
        "audit_events",
        *identity(),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])


def downgrade():
    for table in [
        "audit_events",
        "decisions",
        "model_scores",
        "evidence",
        "cases",
        "alerts",
        "users",
    ]:
        op.drop_table(table)
