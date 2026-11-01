"""Bounded operational aggregates; no customer features or inference schema changes."""

import sqlalchemy as sa

from alembic import op

revision = "0007_operations"
down_revision = "0006_assessment_api"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operational_metrics",
        sa.Column("instance_id", sa.Uuid(), primary_key=True),
        sa.Column("minute", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("total_ms", sa.Float(), nullable=False),
        sa.Column("buckets", sa.JSON(), nullable=False),
        sa.CheckConstraint("count >= 0 AND total_ms >= 0", name="ck_metric_values"),
    )
    op.create_index("ix_operational_metrics_minute", "operational_metrics", ["minute"])


def downgrade():
    op.drop_table("operational_metrics")
