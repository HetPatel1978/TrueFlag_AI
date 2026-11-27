"""Durable fenced assessment jobs and narrowly scoped non-login service identities."""

import sqlalchemy as sa

from alembic import op

revision = "0005_assessment_jobs"
down_revision = "0004_assessments"
branch_labels = None
depends_on = None

IMMUTABLE = (
    "id",
    "created_at",
    "case_id",
    "actor_id",
    "run_id",
    "expected_version",
    "policy",
    "key_sha256",
    "request_sha256",
    "snapshot",
)


def upgrade():
    op.create_table(
        "assessment_workers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("provisioned_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "assessment_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("policy", sa.String(20), nullable=False),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("assessment_workers.id")),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("assessments.id"), unique=True),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("fallback_route", sa.String(20)),
        sa.UniqueConstraint("run_id", name="uq_job_run"),
        sa.UniqueConstraint("key_sha256", name="uq_job_key"),
        sa.CheckConstraint("policy IN ('Efficiency','Balanced','Coverage')", name="ck_job_policy"),
        sa.CheckConstraint("expected_version >= 1", name="ck_job_version"),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="ck_job_attempts"),
        sa.CheckConstraint(
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
    )
    op.create_index("ix_assessment_jobs_case_id", "assessment_jobs", ["case_id"])
    op.create_index("ix_job_ready", "assessment_jobs", ["status", "available_at", "id"])
    op.create_index("ix_job_expiry", "assessment_jobs", ["status", "lease_until"])
    pg = op.get_bind().dialect.name == "postgresql"
    comparisons = " OR ".join(
        f"NEW.{name} IS DISTINCT FROM OLD.{name}"
        if name != "snapshot"
        else (
            "NEW.snapshot::jsonb IS DISTINCT FROM OLD.snapshot::jsonb"
            if pg
            else "NEW.snapshot IS NOT OLD.snapshot"
        )
        for name in IMMUTABLE
    )
    if pg:
        op.execute(f"""CREATE FUNCTION protect_assessment_jobs() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'immutable_job_history'; END IF;
        IF OLD.status IN ('succeeded','failed') OR {comparisons}
        THEN RAISE EXCEPTION 'immutable_job_history'; END IF; RETURN NEW; END; $$""")
        op.execute("""CREATE TRIGGER protect_assessment_jobs BEFORE UPDATE OR DELETE ON assessment_jobs
            FOR EACH ROW EXECUTE FUNCTION protect_assessment_jobs()""")
        op.execute("""CREATE TRIGGER protect_truncate_assessment_jobs BEFORE TRUNCATE ON assessment_jobs
            FOR EACH STATEMENT EXECUTE FUNCTION protect_assessment_jobs()""")
        op.execute("""CREATE FUNCTION protect_job_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF OLD.action LIKE 'assessment.job.%' THEN RAISE EXCEPTION 'immutable_job_audit'; END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$""")
        op.execute("""CREATE TRIGGER protect_job_audit BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION protect_job_audit()""")
    else:
        op.execute(f"""CREATE TRIGGER protect_assessment_jobs_update BEFORE UPDATE ON assessment_jobs
            WHEN OLD.status IN ('succeeded','failed') OR {comparisons}
            BEGIN SELECT RAISE(ABORT, 'immutable_job_history'); END""")
        op.execute("""CREATE TRIGGER protect_assessment_jobs_delete BEFORE DELETE ON assessment_jobs
            BEGIN SELECT RAISE(ABORT, 'immutable_job_history'); END""")
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER protect_job_audit_{action.lower()} BEFORE {action} ON audit_events
                WHEN OLD.action LIKE 'assessment.job.%'
                BEGIN SELECT RAISE(ABORT, 'immutable_job_audit'); END""")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM assessment_jobs")):
        raise RuntimeError("Job history exists; downgrade refused")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER protect_job_audit ON audit_events")
        op.execute("DROP FUNCTION protect_job_audit()")
        op.execute("DROP TRIGGER protect_assessment_jobs ON assessment_jobs")
        op.execute("DROP TRIGGER protect_truncate_assessment_jobs ON assessment_jobs")
        op.execute("DROP FUNCTION protect_assessment_jobs()")
    else:
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER protect_job_audit_{action}")
    op.drop_table("assessment_jobs")
    op.drop_table("assessment_workers")
