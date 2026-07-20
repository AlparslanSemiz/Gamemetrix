"""Track price backfill attempts, including empty provider results.

Revision ID: 20260720_0002
Revises: 20260720_0001
"""

from alembic import op


revision = "20260720_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS prices_refreshed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.drop_column("games", "prices_refreshed_at")
