"""Immutable human casework journal. Apply only through an authorized migration."""

import sqlalchemy as sa

from alembic import op

revision = "0018_human_casework"
down_revision = "0017_live_provider"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "casework_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("binding", sa.JSON(), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.Uuid(),
            sa.ForeignKey("audit_events.id"),
            nullable=False,
            unique=True,
        ),
        sa.UniqueConstraint("case_id", "revision", name="uq_casework_revision"),
        sa.UniqueConstraint("actor_id", "key_sha256", name="uq_casework_idempotency"),
        sa.UniqueConstraint("case_id", "id", name="uq_casework_parent_scope"),
        sa.ForeignKeyConstraint(
            ["case_id", "parent_id"],
            ["casework_entries.case_id", "casework_entries.id"],
            name="fk_casework_parent",
        ),
        sa.CheckConstraint("revision BETWEEN 1 AND 1000", name="ck_casework_revision"),
        sa.CheckConstraint(
            "kind IN ('note','information_request','information_response','finding_review','escalation','supervisor_response','resolution')",
            name="ck_casework_kind",
        ),
        sa.CheckConstraint(
            "length(CAST(payload AS TEXT))<=12288 AND length(CAST(binding AS TEXT))<=8192",
            name="ck_casework_bounds",
        ),
    )
    op.create_index("ix_casework_entries_case_id", "casework_entries", ["case_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_human_casework() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'immutable_human_casework'; END; $$""")
        op.execute(
            "CREATE TRIGGER immutable_human_casework BEFORE UPDATE OR DELETE ON casework_entries FOR EACH ROW EXECUTE FUNCTION protect_human_casework()"
        )
        op.execute(
            "CREATE TRIGGER immutable_human_casework_truncate BEFORE TRUNCATE ON casework_entries FOR EACH STATEMENT EXECUTE FUNCTION protect_human_casework()"
        )
        op.execute("""CREATE FUNCTION require_casework_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NOT EXISTS (SELECT 1 FROM audit_events WHERE id=NEW.audit_event_id
          AND actor_id=NEW.actor_id AND resource_id=NEW.case_id::text
          AND action='evidence.casework.'||NEW.kind
          AND details->>'entry_id'=NEW.id::text
          AND details->>'content_sha256'=NEW.content_sha256)
        THEN RAISE EXCEPTION 'invalid_casework_audit'; END IF; RETURN NEW; END; $$""")
        op.execute(
            "CREATE CONSTRAINT TRIGGER casework_audit AFTER INSERT ON casework_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_casework_audit()"
        )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM casework_entries")):
        raise RuntimeError("Refusing downgrade with retained human casework history")
    op.drop_table("casework_entries")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION protect_human_casework()")
        op.execute("DROP FUNCTION require_casework_audit()")
