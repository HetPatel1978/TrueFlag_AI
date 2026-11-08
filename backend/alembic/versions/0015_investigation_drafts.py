"""Durable simulated investigator drafts and immutable usage provenance."""

import sqlalchemy as sa

from alembic import op

revision = "0015_investigation_drafts"
down_revision = "0014_investigation_foundation"
branch_labels = None
depends_on = None

TABLES = (
    "investigation_draft_runs",
    "investigation_draft_requests",
    "investigation_draft_jobs",
    "investigation_draft_attempts",
    "investigation_draft_receipts",
    "investigation_drafts",
)


def protections():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""CREATE FUNCTION protect_draft_history() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable_investigation_draft_history'; END; $$""")
    for table in TABLES:
        if table != "investigation_draft_jobs":
            op.execute(
                f"CREATE TRIGGER protect_draft_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_draft_history()"
            )
        op.execute(
            f"CREATE TRIGGER protect_draft_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION protect_draft_history()"
        )
    op.execute("""CREATE FUNCTION protect_draft_job() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF TG_OP='DELETE' THEN RAISE EXCEPTION 'retained_draft_history'; END IF;
      IF NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.attempts<OLD.attempts OR
         (OLD.status IN ('succeeded','abstained','failed','invalidated') AND NEW.status!=OLD.status AND NEW.status!='invalidated')
      THEN RAISE EXCEPTION 'invalid_draft_transition'; END IF; RETURN NEW; END; $$""")
    op.execute(
        "CREATE TRIGGER protect_draft_job BEFORE UPDATE OR DELETE ON investigation_draft_jobs FOR EACH ROW EXECUTE FUNCTION protect_draft_job()"
    )
    op.execute("""CREATE FUNCTION require_draft_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF NOT EXISTS(SELECT 1 FROM investigation_draft_jobs WHERE run_id=NEW.id)
      OR NOT EXISTS(SELECT 1 FROM investigation_draft_requests WHERE run_id=NEW.id)
      OR NEW.configuration->>'provider'!='deterministic_fake' OR NEW.configuration->>'mode'!='simulation'
      OR (NEW.configuration->>'max_cost_usd')::numeric!=0 THEN
      RAISE EXCEPTION 'invalid_draft_envelope'; END IF; RETURN NEW; END; $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER require_draft_envelope AFTER INSERT ON investigation_draft_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_draft_envelope()"
    )
    op.execute("""CREATE FUNCTION require_draft_publication() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE rid uuid; s text; n integer; BEGIN
      rid:=NEW.run_id; SELECT status INTO s FROM investigation_draft_jobs WHERE run_id=rid;
      SELECT count(*) INTO n FROM investigation_drafts WHERE run_id=rid;
      IF (s IN ('succeeded','abstained') AND n!=1) OR
        (n>0 AND (s IS NULL OR s NOT IN ('succeeded','abstained','invalidated'))) THEN
        RAISE EXCEPTION 'incomplete_draft_publication'; END IF;
      IF n>0 AND NOT EXISTS(SELECT 1 FROM investigation_drafts d
        JOIN investigation_draft_receipts r ON r.attempt_id=d.attempt_id AND r.status='completed'
        WHERE d.run_id=rid) THEN RAISE EXCEPTION 'missing_draft_receipt'; END IF;
      RETURN NEW; END; $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER require_draft_publication AFTER INSERT OR UPDATE ON investigation_draft_jobs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_draft_publication()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER require_draft_publication AFTER INSERT ON investigation_drafts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_draft_publication()"
    )
    op.execute("""CREATE FUNCTION require_draft_budget() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE cfg json; spent bigint; BEGIN
      SELECT configuration INTO cfg FROM investigation_draft_runs WHERE id=NEW.run_id;
      SELECT sum(input_reservation+output_reservation) INTO spent FROM investigation_draft_attempts WHERE run_id=NEW.run_id;
      IF spent>(cfg->>'total_token_budget')::bigint OR NEW.input_reservation>(cfg->>'max_input_tokens')::integer
      OR NEW.output_reservation>(cfg->>'max_output_tokens')::integer OR NEW.attempt>(cfg->>'max_attempts')::integer
      THEN RAISE EXCEPTION 'draft_budget_exceeded'; END IF; RETURN NEW; END; $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER require_draft_budget AFTER INSERT ON investigation_draft_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_draft_budget()"
    )


def guard_downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Refusing to erase retained investigation draft history")
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM audit_events WHERE action LIKE 'evidence.investigation.draft.%'"
        )
    ):
        raise RuntimeError("Refusing to erase investigation draft audit history")
    if op.get_bind().dialect.name == "postgresql":
        for function in (
            "require_draft_budget",
            "require_draft_publication",
            "require_draft_envelope",
            "protect_draft_job",
            "protect_draft_history",
        ):
            op.execute(f"DROP FUNCTION {function}() CASCADE")


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "investigation_draft_runs",
        sa.Column("parent_run_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("parent_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(CAST(configuration AS TEXT))<=4096", name="ck_draft_config_size"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id", "actor_id", "parent_manifest_sha256"],
            [
                "investigation_runs.id",
                "investigation_runs.actor_id",
                "investigation_runs.manifest_sha256",
            ],
            name="fk_draft_parent_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "actor_id", "manifest_sha256", name="uq_draft_request_scope"),
        sa.UniqueConstraint("id", "manifest_sha256", name="uq_draft_result_scope"),
        sa.UniqueConstraint("parent_run_id", "config_sha256", name="uq_draft_intent"),
    )
    op.create_table(
        "investigation_draft_attempts",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_sha256", sa.String(length=64), nullable=False),
        sa.Column("packet_sha256", sa.String(length=64), nullable=False),
        sa.Column("minimized_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_reservation", sa.Integer(), nullable=False),
        sa.Column("output_reservation", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 3 AND input_reservation BETWEEN 1 AND 65536 AND output_reservation BETWEEN 256 AND 16384",
            name="ck_draft_attempt_budget",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["investigation_draft_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "run_id", name="uq_draft_attempt_scope"),
        sa.UniqueConstraint("run_id", "attempt", name="uq_draft_attempt"),
    )
    op.create_table(
        "investigation_draft_jobs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "(status='running' AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND deadline IS NOT NULL AND attempts>0) OR (status!='running' AND worker_id IS NULL AND lease_token IS NULL AND lease_until IS NULL AND deadline IS NULL)",
            name="ck_draft_job_lease",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','abstained','failed','invalidated') AND attempts BETWEEN 0 AND 3",
            name="ck_draft_job_state",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["investigation_draft_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["investigation_workers.id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("lease_token"),
    )
    op.create_index(
        "ix_draft_job_claim", "investigation_draft_jobs", ["status", "not_before"], unique=False
    )
    op.create_table(
        "investigation_draft_requests",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "actor_id", "manifest_sha256"],
            [
                "investigation_draft_runs.id",
                "investigation_draft_runs.actor_id",
                "investigation_draft_runs.manifest_sha256",
            ],
            name="fk_draft_request_scope",
        ),
        sa.PrimaryKeyConstraint("actor_id", "idempotency_key"),
    )
    op.create_table(
        "investigation_draft_receipts",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed','provider_timeout','provider_unavailable','provider_incomplete','provider_refused','invalid_provider_output','verification_failed','budget_exhausted','authorization_revoked','input_invalidated','worker_revoked','lease_expired','database_unavailable')",
            name="ck_draft_receipt_status",
        ),
        sa.CheckConstraint(
            "elapsed_ms IS NULL OR elapsed_ms BETWEEN 0 AND 60000", name="ck_draft_elapsed"
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["investigation_draft_attempts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_table(
        "investigation_drafts",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(CAST(body AS TEXT))<=524288", name="ck_draft_body_size"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "run_id"],
            ["investigation_draft_attempts.id", "investigation_draft_attempts.run_id"],
            name="fk_draft_result_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["investigation_draft_attempts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "manifest_sha256"],
            ["investigation_draft_runs.id", "investigation_draft_runs.manifest_sha256"],
            name="fk_draft_result_manifest",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["investigation_draft_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id"),
        sa.UniqueConstraint("run_id"),
    )
    # ### end Alembic commands ###
    protections()


def downgrade():
    guard_downgrade()
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("investigation_drafts")
    op.drop_table("investigation_draft_receipts")
    op.drop_table("investigation_draft_requests")
    op.drop_index("ix_draft_job_claim", table_name="investigation_draft_jobs")
    op.drop_table("investigation_draft_jobs")
    op.drop_table("investigation_draft_attempts")
    op.drop_table("investigation_draft_runs")
    # ### end Alembic commands ###
