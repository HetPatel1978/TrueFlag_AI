"""Durable ingestion receipts; no rewrite of existing scientific or business data."""

import sqlalchemy as sa

from alembic import op

revision = "0002_alert_ingestion"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_ingestions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("key_sha256", name="uq_alert_ingestions_key"),
    )
    op.create_index("ix_alert_ingestions_alert_id", "alert_ingestions", ["alert_id"])


def downgrade():
    op.drop_index("ix_alert_ingestions_alert_id", table_name="alert_ingestions")
    op.drop_table("alert_ingestions")
