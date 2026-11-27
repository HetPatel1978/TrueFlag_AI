"""Private CSV upload receipts; no alert/assessment schema changes."""

import sqlalchemy as sa

from alembic import op

revision = "0008_csv_staging"
down_revision = "0007_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "csv_uploads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *[
            sa.Column(n, sa.Integer(), nullable=False)
            for n in ("size_bytes", "row_count", "column_count")
        ],
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(40), nullable=False, unique=True),
        sa.Column("csv_contract_version", sa.String(60), nullable=False),
        sa.Column("feature_contract_version", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.Uuid(),
            sa.ForeignKey("audit_events.id"),
            nullable=False,
            unique=True,
        ),
        sa.UniqueConstraint("actor_id", "key_sha256", name="uq_csv_actor_key"),
        sa.CheckConstraint("status IN ('staged','expired')", name="ck_csv_status"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 8388608", name="ck_csv_size"),
        sa.CheckConstraint("row_count > 0 AND row_count <= 10000", name="ck_csv_rows"),
        sa.CheckConstraint("column_count > 0 AND column_count <= 128", name="ck_csv_columns"),
        sa.CheckConstraint("expires_at > created_at", name="ck_csv_expiry"),
    )
    op.create_index(
        "ix_csv_actor_status_expiry", "csv_uploads", ["actor_id", "status", "expires_at"]
    )
    op.create_index("ix_csv_status_expiry", "csv_uploads", ["status", "expires_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM csv_uploads")):
        raise RuntimeError("Refusing to erase CSV upload receipts")
    op.drop_table("csv_uploads")
