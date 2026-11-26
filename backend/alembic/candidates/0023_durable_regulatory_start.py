"""Candidate only: require frozen regulatory context before any deferred provider attempt."""

import sqlalchemy as sa

from alembic import op

revision = "0023_durable_regulatory_start"
down_revision = "0022_claude_development_scope"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""CREATE FUNCTION require_queued_regulatory_context() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r investigation_draft_runs%ROWTYPE;
    BEGIN
      SELECT * INTO r FROM investigation_draft_runs WHERE id=NEW.run_id;
      IF r.configuration::jsonb ? 'regulatory_query' AND (
        COALESCE(r.configuration->>'regulatory_authority_sha256','') !~ '^[a-f0-9]{64}$'
        OR NOT EXISTS (
        SELECT 1 FROM draft_regulatory_bindings b
        JOIN investigation_runs p ON p.id=b.parent_run_id
        WHERE b.run_id=r.id AND b.actor_id=r.actor_id AND b.parent_run_id=r.parent_run_id
          AND b.case_id=p.case_id AND b.run_manifest_sha256=r.manifest_sha256
          AND b.body::jsonb->'query'=r.configuration::jsonb->'regulatory_query'
          AND b.body::jsonb->'snapshot'=p.input_manifest::jsonb->'snapshot'
          AND b.body->>'binding_sha256'=b.binding_sha256
          AND b.body->>'packet_sha256'=NEW.packet_sha256
          AND b.body->'result'->>'status'='available'
          AND b.body::jsonb->'grounding' IS NOT NULL
          AND b.body::jsonb->'grounding'<>'null'::jsonb
      )) THEN RAISE EXCEPTION 'missing_queued_regulatory_binding'; END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE TRIGGER require_queued_regulatory_context BEFORE INSERT
        ON investigation_draft_attempts FOR EACH ROW EXECUTE FUNCTION require_queued_regulatory_context()""")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM investigation_draft_runs WHERE configuration::jsonb ? 'regulatory_query'"
        )
    ):
        raise RuntimeError(
            "Refusing to remove safeguards for retained queued regulatory investigations"
        )
    op.execute("DROP TRIGGER require_queued_regulatory_context ON investigation_draft_attempts")
    op.execute("DROP FUNCTION require_queued_regulatory_context()")
