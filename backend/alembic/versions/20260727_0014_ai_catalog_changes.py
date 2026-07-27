"""Store AI-driven catalog mutations for the admin activity feed.

Revision ID: 20260727_0014
Revises: 20260727_0013
"""

from alembic import op
import sqlalchemy as sa


revision = "20260727_0014"
down_revision = "20260727_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_catalog_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("game_title", sa.String(length=160), nullable=False),
        sa.Column("game_slug", sa.String(length=180), nullable=False),
        sa.Column("change_type", sa.String(length=48), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("after_values", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_catalog_changes_id", "ai_catalog_changes", ["id"])
    op.create_index("ix_ai_catalog_changes_game_id", "ai_catalog_changes", ["game_id"])
    op.create_index("ix_ai_catalog_changes_game_slug", "ai_catalog_changes", ["game_slug"])
    op.create_index("ix_ai_catalog_changes_change_type", "ai_catalog_changes", ["change_type"])
    op.create_index("ix_ai_catalog_changes_created_at", "ai_catalog_changes", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_catalog_changes")
