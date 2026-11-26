"""Add persistent upload workspaces without deleting or rewriting historical records."""

import sqlalchemy as sa

from alembic import op

revision = "0019_upload_sessions"
down_revision = "0018_human_casework"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_sha256", sa.String(64), nullable=False),
        sa.Column("creation_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("actor_id", "key_sha256", name="uq_upload_session_key"),
    )
    op.create_index("ix_upload_sessions_actor_id", "upload_sessions", ["actor_id"])
    op.create_table(
        "upload_session_items",
        sa.Column("upload_id", sa.Uuid(), sa.ForeignKey("csv_uploads.id"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("upload_sessions.id"), nullable=False),
    )
    op.create_index("ix_upload_session_items_session_id", "upload_session_items", ["session_id"])
    op.create_table(
        "upload_workspaces",
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("upload_sessions.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_upload_workspace_version"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM upload_sessions")):
        raise RuntimeError("Refusing downgrade with retained upload sessions")
    op.drop_table("upload_workspaces")
    op.drop_table("upload_session_items")
    op.drop_table("upload_sessions")
