"""Candidate external draft envelope; preserves all immutable history and budget triggers."""

import sqlalchemy as sa

from alembic import op

revision = "0017_live_provider"
down_revision = "0016_snapshot_clock"
branch_labels = None
depends_on = None

FAKE = """configuration->>'provider'='deterministic_fake'
 AND configuration->>'model'='trueflag-fake-selection.v1'
 AND configuration->>'mode'='simulation'
 AND (configuration->>'max_cost_usd')::numeric=0"""
LIVE = """configuration->>'provider'='luminal'
 AND configuration->>'model'='deepseek-ai/DeepSeek-V4.1-Flash'
 AND configuration->>'mode'='provider_candidate'
 AND configuration->>'base_url'='https://flash.luminal.cloud/v1'
 AND (configuration->>'max_cost_usd')::numeric>0
 AND (configuration->>'max_cost_usd')::numeric<=5"""


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
    envelope("(" + FAKE + ") OR (" + LIVE + ")")


def downgrade():
    count = (
        op.get_bind().scalar(
            sa.text(
                "SELECT count(*) FROM investigation_draft_runs WHERE configuration->>'provider'!='deterministic_fake'"
            )
        )
        if op.get_bind().dialect.name == "postgresql"
        else op.get_bind().scalar(
            sa.text(
                "SELECT count(*) FROM investigation_draft_runs WHERE json_extract(configuration,'$.provider')!='deterministic_fake'"
            )
        )
    )
    if count:
        raise RuntimeError("Refusing downgrade with retained external draft history")
    envelope(FAKE)
