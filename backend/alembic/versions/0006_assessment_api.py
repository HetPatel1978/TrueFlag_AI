"""Durable authenticated assessment API budget; no feature or model schema change."""

import sqlalchemy as sa

from alembic import op

revision = "0006_assessment_api"
down_revision = "0005_assessment_jobs"
branch_labels = None
depends_on = None


def audit_guard(include_reads):
    condition = "OLD.action LIKE 'assessment.job.%'"
    if include_reads:
        condition += " OR OLD.action IN ('assessment.history_read','assessment.detail_read')"
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"""CREATE OR REPLACE FUNCTION protect_job_audit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN IF {condition} THEN
            RAISE EXCEPTION 'immutable_job_audit'; END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$""")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER protect_job_audit_{action.lower()}")
            op.execute(f"""CREATE TRIGGER protect_job_audit_{action.lower()} BEFORE {action}
                ON audit_events WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'immutable_job_audit'); END""")


def upgrade():
    op.create_table(
        "assessment_api_throttles",
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("request_count >= 1", name="ck_assessment_api_count"),
    )
    audit_guard(True)


def downgrade():
    audit_guard(False)
    op.drop_table("assessment_api_throttles")
