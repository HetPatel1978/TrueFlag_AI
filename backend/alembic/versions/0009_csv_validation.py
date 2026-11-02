"""Versioned value-free CSV validation previews; no canonical ingestion writes."""

import sqlalchemy as sa

from alembic import op

revision = "0009_csv_validation"
down_revision = "0008_csv_staging"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "csv_validations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_id", sa.Uuid(), sa.ForeignKey("csv_uploads.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        *[
            sa.Column(name, sa.String(64), nullable=False)
            for name in ("mapping_sha256", "upload_sha256", "feature_contract_sha256")
        ],
        *[
            sa.Column(name, sa.String(60), nullable=False)
            for name in ("mapping_version", "validator_version")
        ],
        sa.Column("units", sa.String(40), nullable=False),
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("total_rows", "valid_rows", "invalid_rows", "warning_rows")
        ],
        sa.Column(
            "audit_event_id",
            sa.Uuid(),
            sa.ForeignKey("audit_events.id"),
            unique=True,
            nullable=False,
        ),
        sa.UniqueConstraint("upload_id", "mapping_sha256", name="uq_csv_validation_mapping"),
        sa.UniqueConstraint("upload_id", "version", name="uq_csv_validation_version"),
        sa.CheckConstraint(
            "version >= 1 AND total_rows > 0 AND total_rows <= 10000",
            name="ck_csv_validation_version",
        ),
        sa.CheckConstraint(
            "valid_rows >= 0 AND invalid_rows >= 0 AND valid_rows + invalid_rows = total_rows AND warning_rows >= 0 AND warning_rows <= total_rows",
            name="ck_csv_validation_counts",
        ),
    )
    op.create_table(
        "csv_validation_issues",
        sa.Column(
            "validation_id", sa.Uuid(), sa.ForeignKey("csv_validations.id"), primary_key=True
        ),
        sa.Column("row_number", sa.Integer(), primary_key=True),
        sa.Column("invalid", sa.Boolean(), nullable=False),
        sa.Column("has_warnings", sa.Boolean(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.CheckConstraint("row_number >= 2 AND row_number <= 10001", name="ck_csv_issue_row"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM csv_validations")):
        raise RuntimeError("Refusing to erase CSV validation history")
    op.drop_table("csv_validation_issues")
    op.drop_table("csv_validations")
