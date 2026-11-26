"""Candidate-only immutable binding for existing investigation draft jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0021_regulatory_draft_bindings"
down_revision = "0020_claude_provider"
branch_labels = None
depends_on = None


def upgrade():
    from app.models.regulatory_drafts import DraftRegulatoryBinding

    DraftRegulatoryBinding.__table__.create(op.get_bind())
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER protect_regulatory_binding BEFORE UPDATE OR DELETE ON draft_regulatory_bindings FOR EACH ROW EXECUTE FUNCTION protect_draft_history()"
        )
        op.execute(
            "CREATE TRIGGER protect_regulatory_binding_truncate BEFORE TRUNCATE ON draft_regulatory_bindings FOR EACH STATEMENT EXECUTE FUNCTION protect_draft_history()"
        )
        op.execute("""CREATE FUNCTION require_regulatory_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.configuration->>'regulatory_binding_sha256' IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM draft_regulatory_bindings b JOIN investigation_runs p ON p.id=b.parent_run_id
          WHERE b.run_id=NEW.id AND b.actor_id=NEW.actor_id AND b.parent_run_id=NEW.parent_run_id
          AND b.case_id=p.case_id AND b.run_manifest_sha256=NEW.manifest_sha256
          AND b.binding_sha256=NEW.configuration->>'regulatory_binding_sha256')
          THEN RAISE EXCEPTION 'missing_regulatory_draft_binding'; END IF; RETURN NEW; END; $$""")
        op.execute(
            "CREATE CONSTRAINT TRIGGER require_regulatory_binding AFTER INSERT ON investigation_draft_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_regulatory_binding()"
        )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM draft_regulatory_bindings")):
        raise RuntimeError("Refusing to erase retained regulatory draft bindings")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER require_regulatory_binding ON investigation_draft_runs")
        op.execute("DROP FUNCTION require_regulatory_binding()")
    op.drop_table("draft_regulatory_bindings")
