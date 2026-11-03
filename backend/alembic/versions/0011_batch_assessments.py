"""Explicit batch assessment intent, membership, request receipts; existing ML queue reused."""

import sqlalchemy as sa

from alembic import op

revision = "0011_batch_assessments"
down_revision = "0010_csv_imports"
branch_labels = None
depends_on = None

ROOT_FROZEN = (
    "id",
    "created_at",
    "import_id",
    "actor_id",
    "import_sha256",
    "policy",
    "model_version",
    "model_sha256",
    "policy_version",
    "policy_sha256",
    "group_size",
    "audit_event_id",
)
ITEM_FROZEN = (
    "batch_id",
    "case_id",
    "alert_id",
    "source_row_number",
    "case_version",
    "eligible",
    "run_id",
)


def guard(table, name, update, delete="TRUE"):
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP = 'UPDATE' THEN IF {update} THEN RAISE EXCEPTION 'immutable_batch_record'; END IF; RETURN NEW; END IF; IF {delete} THEN RAISE EXCEPTION 'immutable_batch_record'; END IF; RETURN OLD; END; $$"
        )
        op.execute(
            f"CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()"
        )
    else:
        for action, condition in (("UPDATE", update), ("DELETE", delete)):
            op.execute(
                f"CREATE TRIGGER {name}_{action.lower()} BEFORE {action} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'immutable_batch_record'); END"
            )


def upgrade():
    op.create_table(
        "batch_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("csv_imports.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("import_sha256", sa.String(64), nullable=False),
        sa.Column("policy", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("model_sha256", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(180), nullable=False),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("group_size", sa.Integer(), nullable=False),
        sa.Column("backpressure_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "audit_event_id",
            sa.Uuid(),
            sa.ForeignKey("audit_events.id"),
            nullable=False,
            unique=True,
        ),
        sa.UniqueConstraint(
            "import_id",
            "policy",
            "model_sha256",
            "policy_sha256",
            name="uq_batch_assessment_intent",
        ),
        sa.CheckConstraint(
            "policy IN ('Efficiency','Balanced','Coverage')", name="ck_batch_policy"
        ),
        sa.CheckConstraint(
            "status IN ('active','completed','partially_completed','failed','stopped')",
            name="ck_batch_status",
        ),
        sa.CheckConstraint(
            "group_size >= 1 AND group_size <= 25 AND backpressure_count >= 0",
            name="ck_batch_limits",
        ),
    )
    op.create_index(
        "ix_batch_assessment_ready", "batch_assessments", ["status", "available_at", "id"]
    )
    op.create_table(
        "batch_assessment_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.Uuid(), sa.ForeignKey("batch_assessments.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("actor_id", "key_sha256", name="uq_batch_assessment_key"),
    )
    op.create_table(
        "batch_assessment_items",
        sa.Column("batch_id", sa.Uuid(), sa.ForeignKey("batch_assessments.id"), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), primary_key=True),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("originated", sa.Boolean(), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("assessment_jobs.id")),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("assessments.id")),
        sa.UniqueConstraint("batch_id", "source_row_number", name="uq_batch_assessment_row"),
        sa.CheckConstraint(
            "source_row_number >= 2 AND source_row_number <= 10001 AND case_version >= 1",
            name="ck_batch_item_source",
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND job_id IS NULL AND assessment_id IS NULL AND reason_code IS NULL AND originated = false) OR (status = 'job' AND job_id IS NOT NULL AND assessment_id IS NULL AND reason_code IS NULL) OR (status IN ('skipped','failed') AND job_id IS NULL AND reason_code IS NOT NULL AND originated = false)",
            name="ck_batch_item_state",
        ),
    )
    op.create_index(
        "ix_batch_item_ready", "batch_assessment_items", ["batch_id", "status", "source_row_number"]
    )
    op.create_index("ix_batch_item_job", "batch_assessment_items", ["job_id"])
    op.create_index(
        "uq_batch_job_origin",
        "batch_assessment_items",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("originated = true"),
        sqlite_where=sa.text("originated = true"),
    )
    pg = op.get_bind().dialect.name == "postgresql"

    def changed(names):
        return " OR ".join(
            f"NEW.{n} IS DISTINCT FROM OLD.{n}" if pg else f"NEW.{n} IS NOT OLD.{n}" for n in names
        )

    guard(
        "batch_assessments",
        "protect_batch_root",
        "OLD.status != 'active' OR " + changed(ROOT_FROZEN),
    )
    guard(
        "batch_assessment_items",
        "protect_batch_item",
        "OLD.status != 'ready' OR " + changed(ITEM_FROZEN),
    )
    guard("batch_assessment_requests", "protect_batch_request", "TRUE")
    guard(
        "audit_events",
        "protect_batch_audit",
        "OLD.action LIKE 'batch.assessment.%'",
        "OLD.action LIKE 'batch.assessment.%'",
    )
    if pg:
        op.execute(
            "CREATE FUNCTION block_batch_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable_batch_record'; END; $$"
        )
        for table in ("batch_assessments", "batch_assessment_items", "batch_assessment_requests"):
            op.execute(
                f"CREATE TRIGGER protect_batch_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION block_batch_truncate()"
            )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM batch_assessments")):
        raise RuntimeError("Refusing to erase batch assessment history")
    pg = op.get_bind().dialect.name == "postgresql"
    for table, name in (
        ("batch_assessments", "protect_batch_root"),
        ("batch_assessment_items", "protect_batch_item"),
        ("batch_assessment_requests", "protect_batch_request"),
        ("audit_events", "protect_batch_audit"),
    ):
        if pg:
            op.execute(f"DROP TRIGGER {name} ON {table}")
            op.execute(f"DROP FUNCTION {name}()")
            if table != "audit_events":
                op.execute(f"DROP TRIGGER protect_batch_truncate ON {table}")
        else:
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER {name}_{action}")
    if pg:
        op.execute("DROP FUNCTION block_batch_truncate()")
    for table in ("batch_assessment_requests", "batch_assessment_items", "batch_assessments"):
        op.drop_table(table)
