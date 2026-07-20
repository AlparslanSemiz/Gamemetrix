"""Player mode tags (singleplayer / multiplayer / coop) for catalog filtering.

Revision ID: 20260720_0004
Revises: 20260720_0003
"""

from alembic import op


revision = "20260720_0004"
down_revision = "20260720_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS game_modes JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.drop_column("games", "game_modes")
