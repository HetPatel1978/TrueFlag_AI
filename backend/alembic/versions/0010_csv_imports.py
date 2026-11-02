"""Durable approved CSV import queue, scoped workers and per-row checkpoints."""

import sqlalchemy as sa

from alembic import op

revision = "0010_csv_imports"
down_revision = "0009_csv_validation"
branch_labels = None
depends_on = None

FROZEN = (
    "id",
    "created_at",
    "upload_id",
    "validation_id",
    "actor_id",
    "key_sha256",
    "request_sha256",
    "validation_sha256",
    "snapshot",
    "audit_event_id",
    "source_expires_at",
    "total_rows",
    "valid_rows",
    "invalid_rows",
    "chunk_size",
)
UPLOAD_FIELDS = (
    "id",
    "actor_id",
    "created_at",
    "size_bytes",
    "row_count",
    "column_count",
    "sha256",
    "key_sha256",
    "storage_key",
    "csv_contract_version",
    "feature_contract_version",
    "expires_at",
    "audit_event_id",
)


def _guard(table, label, update, delete, insert=None):
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        checks = f"IF TG_OP = 'UPDATE' THEN IF {update} THEN RAISE EXCEPTION 'immutable_import_record'; END IF; RETURN NEW; END IF; IF TG_OP = 'DELETE' THEN IF {delete} THEN RAISE EXCEPTION 'immutable_import_record'; END IF; RETURN OLD; END IF;"
        if insert:
            checks += f" IF TG_OP = 'INSERT' AND ({insert}) THEN RAISE EXCEPTION 'immutable_import_record'; END IF;"
        op.execute(
            f"CREATE FUNCTION {label}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {checks} RETURN NEW; END; $$"
        )
        op.execute(
            f"CREATE TRIGGER {label} BEFORE UPDATE OR DELETE{' OR INSERT' if insert else ''} ON {table} FOR EACH ROW EXECUTE FUNCTION {label}()"
        )
    else:
        for action, condition in (("UPDATE", update), ("DELETE", delete), ("INSERT", insert)):
            if condition:
                op.execute(
                    f"CREATE TRIGGER {label}_{action.lower()} BEFORE {action} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'immutable_import_record'); END"
                )


def upgrade():
    op.create_table(
        "csv_import_workers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("provisioned_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_table(
        "csv_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *[
            sa.Column(n, sa.Uuid(), sa.ForeignKey(t + ".id"), nullable=False)
            for n, t in (
                ("upload_id", "csv_uploads"),
                ("validation_id", "csv_validations"),
                ("actor_id", "users"),
            )
        ],
        *[
            sa.Column(n, sa.String(64), nullable=False)
            for n in ("key_sha256", "request_sha256", "validation_sha256")
        ],
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.Uuid(),
            sa.ForeignKey("audit_events.id"),
            nullable=False,
            unique=True,
        ),
        *[
            sa.Column(n, sa.DateTime(timezone=True), nullable=False)
            for n in ("source_expires_at", "available_at", "updated_at")
        ],
        sa.Column("status", sa.String(30), nullable=False),
        *[
            sa.Column(n, sa.Integer(), nullable=False)
            for n in (
                "total_rows",
                "valid_rows",
                "invalid_rows",
                "processed_rows",
                "created_rows",
                "reused_rows",
                "conflict_rows",
                "excluded_rows",
                "chunk_size",
                "attempts",
            )
        ],
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("csv_import_workers.id")),
        sa.Column("failure_code", sa.String(40)),
        sa.UniqueConstraint("actor_id", "key_sha256", name="uq_csv_import_actor_key"),
        sa.UniqueConstraint("validation_id", name="uq_csv_import_validation"),
        sa.CheckConstraint(
            "total_rows > 0 AND total_rows <= 10000 AND valid_rows > 0 AND invalid_rows >= 0 AND valid_rows + invalid_rows = total_rows",
            name="ck_csv_import_total",
        ),
        sa.CheckConstraint(
            "processed_rows >= 0 AND processed_rows <= total_rows AND created_rows >= 0 AND reused_rows >= 0 AND conflict_rows >= 0 AND excluded_rows >= 0 AND excluded_rows <= invalid_rows AND created_rows + reused_rows + conflict_rows + excluded_rows = processed_rows",
            name="ck_csv_import_progress",
        ),
        sa.CheckConstraint(
            "chunk_size >= 1 AND chunk_size <= 200 AND attempts >= 0 AND attempts <= 3",
            name="ck_csv_import_limits",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND lease_token IS NULL AND lease_until IS NULL AND worker_id IS NULL) OR (status = 'running' AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND worker_id IS NOT NULL AND attempts >= 1) OR (status IN ('completed','partially_completed','failed') AND lease_token IS NULL AND lease_until IS NULL AND worker_id IS NULL)",
            name="ck_csv_import_state",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','partially_completed') OR (processed_rows = total_rows AND excluded_rows = invalid_rows)",
            name="ck_csv_import_finished",
        ),
    )
    op.create_index("ix_csv_import_ready", "csv_imports", ["status", "available_at", "id"])
    op.create_index("ix_csv_import_expiry", "csv_imports", ["status", "lease_until"])
    op.create_table(
        "csv_import_rows",
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("csv_imports.id"), primary_key=True),
        sa.Column("row_number", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id")),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id")),
        sa.CheckConstraint(
            "row_number >= 2 AND row_number <= 10001", name="ck_csv_import_row_number"
        ),
        sa.CheckConstraint(
            "(status IN ('created','reused') AND alert_id IS NOT NULL AND case_id IS NOT NULL AND reason_code IS NULL) OR (status IN ('invalid','conflict') AND alert_id IS NULL AND case_id IS NULL AND reason_code IS NOT NULL)",
            name="ck_csv_import_row_status",
        ),
    )
    pg = op.get_bind().dialect.name == "postgresql"

    def changed(names):
        return " OR ".join(
            (
                f"NEW.{n}::jsonb IS DISTINCT FROM OLD.{n}::jsonb"
                if n == "snapshot"
                else f"NEW.{n} IS DISTINCT FROM OLD.{n}"
            )
            if pg
            else f"NEW.{n} IS NOT OLD.{n}"
            for n in names
        )

    _guard(
        "csv_imports",
        "guard_csv_import",
        "OLD.status IN ('completed','partially_completed','failed') OR " + changed(FROZEN),
        "TRUE",
    )
    _guard("csv_import_rows", "guard_csv_import_row", "TRUE", "TRUE")
    bound = "EXISTS (SELECT 1 FROM csv_imports WHERE validation_id = OLD.id)"
    _guard("csv_validations", "guard_approved_validation", bound, bound)
    bound_issue = "EXISTS (SELECT 1 FROM csv_imports WHERE validation_id = OLD.validation_id)"
    _guard(
        "csv_validation_issues",
        "guard_approved_issue",
        bound_issue,
        bound_issue,
        "EXISTS (SELECT 1 FROM csv_imports WHERE validation_id = NEW.validation_id)",
    )
    bound_upload = "EXISTS (SELECT 1 FROM csv_imports WHERE upload_id = OLD.id)"
    _guard(
        "csv_uploads",
        "guard_approved_upload",
        f"({bound_upload}) AND ({changed(UPLOAD_FIELDS)})",
        bound_upload,
    )
    _guard(
        "audit_events",
        "guard_import_audit",
        "OLD.action LIKE 'batch.import.%'",
        "OLD.action LIKE 'batch.import.%'",
    )
    if pg:
        op.execute(
            "CREATE FUNCTION block_csv_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable_import_record'; END; $$"
        )
        for table in (
            "csv_imports",
            "csv_import_rows",
            "csv_validations",
            "csv_validation_issues",
            "csv_uploads",
        ):
            op.execute(
                f"CREATE TRIGGER guard_import_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION block_csv_truncate()"
            )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM csv_imports")):
        raise RuntimeError("Refusing to erase import history")
    tables = {
        "csv_imports": "guard_csv_import",
        "csv_import_rows": "guard_csv_import_row",
        "csv_validations": "guard_approved_validation",
        "csv_validation_issues": "guard_approved_issue",
        "csv_uploads": "guard_approved_upload",
        "audit_events": "guard_import_audit",
    }
    pg = op.get_bind().dialect.name == "postgresql"
    for table, label in tables.items():
        if pg:
            op.execute(f"DROP TRIGGER {label} ON {table}")
            op.execute(f"DROP FUNCTION {label}()")
        else:
            for action in ("update", "delete", "insert"):
                op.execute(f"DROP TRIGGER IF EXISTS {label}_{action}")
    if pg:
        for table in list(tables)[:-1]:
            op.execute(f"DROP TRIGGER guard_import_truncate ON {table}")
        op.execute("DROP FUNCTION block_csv_truncate()")
    op.drop_table("csv_import_rows")
    op.drop_table("csv_imports")
    op.drop_table("csv_import_workers")
