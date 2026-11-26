"""Permit the separately gated synthetic Claude provider without changing prior history."""

import sqlalchemy as sa

from alembic import op

revision = "0020_claude_provider"
down_revision = "0019_upload_sessions"
branch_labels = None
depends_on = None

FAKE = """configuration->>'provider'='deterministic_fake'
 AND configuration->>'model'='trueflag-fake-selection.v1'
 AND configuration->>'mode'='simulation' AND (configuration->>'max_cost_usd')::numeric=0"""
LUMINAL = """configuration->>'provider'='luminal'
 AND configuration->>'model'='deepseek-ai/DeepSeek-V4.1-Flash'
 AND configuration->>'mode'='provider_candidate'
 AND configuration->>'base_url'='https://flash.luminal.cloud/v1'
 AND (configuration->>'max_cost_usd')::numeric>0
 AND (configuration->>'max_cost_usd')::numeric<=5"""
CLAUDE = """configuration->>'provider'='anthropic'
 AND configuration->>'model'='claude-sonnet-5-5'
 AND configuration->>'mode'='provider_candidate'
 AND configuration->>'data_scope'='synthetic_only'
 AND configuration->>'base_url'='https://api.anthropic.com/v1'
 AND (configuration->>'max_cost_usd')::numeric>=2.10
 AND (configuration->>'max_cost_usd')::numeric<=5
 AND (configuration->>'max_attempts')::integer=1"""


def envelope(predicate):
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """CREATE OR REPLACE FUNCTION require_draft_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NOT EXISTS(SELECT 1 FROM investigation_draft_jobs WHERE run_id=NEW.id)
        OR NOT EXISTS(SELECT 1 FROM investigation_draft_requests WHERE run_id=NEW.id)
        OR NOT COALESCE((SELECT """
            + predicate
            + """ FROM investigation_draft_runs WHERE id=NEW.id),false)
        THEN RAISE EXCEPTION 'invalid_draft_envelope'; END IF; RETURN NEW; END; $$"""
        )


def upgrade():
    envelope("(" + FAKE + ") OR (" + LUMINAL + ") OR (" + CLAUDE + ")")


def downgrade():
    bind = op.get_bind()
    query = (
        "SELECT count(*) FROM investigation_draft_runs WHERE configuration->>'provider'='anthropic'"
        if bind.dialect.name == "postgresql"
        else "SELECT count(*) FROM investigation_draft_runs WHERE json_extract(configuration,'$.provider')='anthropic'"
    )
    if bind.scalar(sa.text(query)):
        raise RuntimeError("Refusing downgrade with retained Claude draft history")
    envelope("(" + FAKE + ") OR (" + LUMINAL + ")")
