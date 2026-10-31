"""Supervisor role, case access indexes, version integrity and login throttle storage."""

import sqlalchemy as sa

from alembic import op

revision = "0003_case_security"
down_revision = "0002_alert_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.create_check_constraint("ck_user_role", "role IN ('analyst','supervisor','admin')")
    with op.batch_alter_table("cases") as batch:
        batch.create_check_constraint("ck_case_version", "version >= 1")
    op.create_index("ix_cases_assigned_created_id", "cases", ["assigned_to", "created_at", "id"])
    op.create_index("ix_cases_status_created_id", "cases", ["status", "created_at", "id"])
    op.create_table(
        "login_throttles",
        sa.Column("key_sha256", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempt_count >= 1", name="ck_login_attempt_count"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE role = 'supervisor'")):
        raise RuntimeError(
            "Cannot downgrade while supervisor accounts exist; no roles were changed"
        )
    op.drop_table("login_throttles")
    op.drop_index("ix_cases_status_created_id", table_name="cases")
    op.drop_index("ix_cases_assigned_created_id", table_name="cases")
    with op.batch_alter_table("cases") as batch:
        batch.drop_constraint("ck_case_version", type_="check")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.create_check_constraint("ck_user_role", "role IN ('analyst','admin')")
