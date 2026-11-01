"""Append-only assessments and verified explanations, retaining legacy decision contracts."""

import sqlalchemy as sa

from alembic import op

revision = "0004_assessments"
down_revision = "0003_case_security"
branch_labels = None
depends_on = None

PROTECTED = {
    "assessments": None,
    "assessment_explanations": None,
    "model_scores": "score_id",
    "decisions": "decision_id",
    "audit_events": "audit_event_id",
}


def upgrade():
    with op.batch_alter_table("decisions") as batch:
        batch.drop_constraint("ck_decision_route", type_="check")
        batch.alter_column("route", existing_type=sa.String(20), type_=sa.String(40))
        batch.create_check_constraint(
            "ck_decision_route",
            "(processing_status = 'processed' AND route IS NOT NULL AND "
            "route IN ('retain','dismiss','retain_human_review','review_reduction_candidate')) OR "
            "(processing_status = 'failed' AND route IS NULL)",
        )
    op.create_table(
        "assessment_explanations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("verification", sa.JSON(), nullable=False),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *[
            sa.Column(name, sa.String(64), nullable=False)
            for name in ("key_sha256", "request_sha256", "content_sha256", "input_sha256")
        ],
        *[
            sa.Column(name, sa.Uuid(), sa.ForeignKey(target + ".id"), nullable=False, unique=True)
            for name, target in (
                ("score_id", "model_scores"),
                ("decision_id", "decisions"),
                ("explanation_id", "assessment_explanations"),
                ("audit_event_id", "audit_events"),
            )
        ],
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.UniqueConstraint("case_id", "version", name="uq_assessment_case_version"),
        sa.UniqueConstraint("run_id", name="uq_assessment_run"),
        sa.UniqueConstraint("key_sha256", name="uq_assessment_key"),
        sa.CheckConstraint("version >= 1 AND case_version >= 1", name="ck_assessment_version"),
        sa.CheckConstraint("status = 'completed'", name="ck_assessment_completed"),
    )
    op.create_index("ix_assessments_case_id", "assessments", ["case_id"])
    dialect = op.get_bind().dialect.name
    for table, column in PROTECTED.items():
        condition = (
            "TRUE"
            if column is None
            else (f"EXISTS (SELECT 1 FROM assessments WHERE {column} = OLD.id)")
        )
        if dialect == "postgresql":
            op.execute(f"""CREATE FUNCTION protect_{table}() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                IF TG_OP = 'TRUNCATE' THEN RAISE EXCEPTION 'immutable_assessment_record'; END IF;
                IF {condition} THEN RAISE EXCEPTION 'immutable_assessment_record'; END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$""")
            op.execute(f"""CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION protect_{table}()""")
            op.execute(f"""CREATE TRIGGER protect_truncate_{table} BEFORE TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION protect_{table}()""")
        elif dialect == "sqlite":
            for action in ("UPDATE", "DELETE"):
                op.execute(f"""CREATE TRIGGER protect_{table}_{action.lower()}
                    BEFORE {action} ON {table} WHEN {condition}
                    BEGIN SELECT RAISE(ABORT, 'immutable_assessment_record'); END""")
        else:
            raise RuntimeError("Unsupported assessment database")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM assessments")):
        raise RuntimeError("Assessment history exists; destructive downgrade refused")
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM decisions WHERE route IN "
            "('retain_human_review','review_reduction_candidate')"
        )
    ):
        raise RuntimeError("New recommendation records exist; downgrade refused")
    for table in PROTECTED:
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP TRIGGER protect_{table} ON {table}")
            op.execute(f"DROP TRIGGER protect_truncate_{table} ON {table}")
            op.execute(f"DROP FUNCTION protect_{table}()")
        else:
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER protect_{table}_{action}")
    op.drop_index("ix_assessments_case_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("assessment_explanations")
    with op.batch_alter_table("decisions") as batch:
        batch.drop_constraint("ck_decision_route", type_="check")
        batch.alter_column("route", existing_type=sa.String(40), type_=sa.String(20))
        batch.create_check_constraint(
            "ck_decision_route",
            "(processing_status = 'processed' AND route IS NOT NULL AND "
            "route IN ('retain','dismiss')) OR (processing_status = 'failed' AND route IS NULL)",
        )
