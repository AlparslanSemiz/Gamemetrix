"""Index lower(developer) and lower(publisher) for the catalog studio filters.

The studio filters compare `lower(developer) = :value`, which the plain developer
index from revision 0016 cannot serve, so every filtered request scanned the table.

Revision ID: 20261118_0018
Revises: 20260729_0017
"""

from alembic import op


revision = "20261118_0018"
down_revision = "20260729_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_games_developer_lower ON games (lower(developer))")
    op.execute("CREATE INDEX IF NOT EXISTS ix_games_publisher_lower ON games (lower(publisher))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_publisher_lower")
    op.execute("DROP INDEX IF EXISTS ix_games_developer_lower")
