"""Candidate-only one-shot development policy; no edits to historical reservations."""

import sqlalchemy as sa

from alembic import op

revision = "0022_claude_development_scope"
down_revision = "0021_regulatory_draft_bindings"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""CREATE OR REPLACE FUNCTION require_draft_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF NOT EXISTS(SELECT 1 FROM investigation_draft_jobs WHERE run_id=NEW.id)
      OR NOT EXISTS(SELECT 1 FROM investigation_draft_requests WHERE run_id=NEW.id)
      OR NOT COALESCE((SELECT
      (configuration->>'provider'='deterministic_fake' AND configuration->>'model'='trueflag-fake-selection.v1'
        AND configuration->>'mode'='simulation' AND (configuration->>'max_cost_usd')::numeric=0)
      OR (configuration->>'provider'='luminal' AND configuration->>'model'='deepseek-ai/DeepSeek-V4.1-Flash'
        AND configuration->>'mode'='provider_candidate' AND configuration->>'base_url'='https://flash.luminal.cloud/v1'
        AND (configuration->>'max_cost_usd')::numeric>0 AND (configuration->>'max_cost_usd')::numeric<=5)
      OR (configuration->>'provider'='anthropic' AND configuration->>'model'='claude-sonnet-5-5'
        AND configuration->>'mode'='provider_candidate' AND configuration->>'data_scope'='synthetic_only'
        AND configuration->>'base_url'='https://api.anthropic.com/v1' AND (configuration->>'max_attempts')::integer=1
        AND (((configuration->>'max_cost_usd')::numeric>=2.10 AND (configuration->>'max_cost_usd')::numeric<=5
          AND COALESCE(configuration->>'financial_scope','reserved_demo_v1')='reserved_demo_v1')
          OR (configuration->>'financial_scope'='development_no_spend_cap_v1'
            AND configuration->>'purpose'='development_validation'
            AND configuration->>'wire_format'='flat_selection_v2'
            AND (configuration->>'max_cost_usd')::numeric=0
            AND configuration->>'exact_input_sha256' ~ '^[a-f0-9]{64}$')))
      FROM investigation_draft_runs WHERE id=NEW.id),false)
    THEN RAISE EXCEPTION 'invalid_draft_envelope'; END IF; RETURN NEW; END; $$""")


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM investigation_draft_runs WHERE configuration->>'financial_scope'='development_no_spend_cap_v1'"
        )
    ):
        raise RuntimeError("Refusing downgrade with retained development history")
    import importlib.util
    from pathlib import Path

    path = Path(__file__).with_name("0020_claude_provider.py")
    spec = importlib.util.spec_from_file_location("claude_candidate_envelope", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()
