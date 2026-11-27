"""Durable evidence-token clock floor and regression epoch; no source-data updates."""

import sqlalchemy as sa

from alembic import op

revision = "0016_snapshot_clock"
down_revision = "0015_investigation_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "snapshot_clock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("high_water", sa.BigInteger(), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("regressed", sa.Boolean(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id=1", name="ck_snapshot_clock_singleton"),
        sa.CheckConstraint("high_water>=0 AND epoch>=1", name="ck_snapshot_clock_values"),
        sa.PrimaryKeyConstraint("id"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "INSERT INTO snapshot_clock VALUES (1,floor(extract(epoch FROM clock_timestamp()))::bigint,1,false,false)"
        )
        op.execute("""CREATE FUNCTION protect_snapshot_clock() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'retained_snapshot_clock'; END IF;
          IF NEW.id!=OLD.id OR NEW.high_water<OLD.high_water OR (OLD.used AND NOT NEW.used)
            OR (NEW.regressed AND NOT OLD.regressed AND
                 (NEW.epoch!=OLD.epoch+1 OR NEW.high_water!=OLD.high_water))
            OR ((NOT NEW.regressed OR OLD.regressed) AND NEW.epoch!=OLD.epoch)
          THEN RAISE EXCEPTION 'invalid_snapshot_clock_transition'; END IF;
          RETURN NEW;
        END; $$""")
        op.execute(
            "CREATE TRIGGER protect_snapshot_clock BEFORE UPDATE OR DELETE ON snapshot_clock FOR EACH ROW EXECUTE FUNCTION protect_snapshot_clock()"
        )
        op.execute(
            "CREATE TRIGGER protect_snapshot_clock_truncate BEFORE TRUNCATE ON snapshot_clock FOR EACH STATEMENT EXECUTE FUNCTION protect_snapshot_clock()"
        )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM snapshot_clock WHERE used=true OR epoch>1 OR regressed=true")
    ):
        raise RuntimeError("Refusing to erase retained snapshot clock history")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION protect_snapshot_clock() CASCADE")
    op.drop_table("snapshot_clock")
