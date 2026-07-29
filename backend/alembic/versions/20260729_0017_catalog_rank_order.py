"""Cover the deterministic default catalog ordering.

Revision ID: 20260729_0017
Revises: 20260727_0016
"""

from alembic import op


revision = "20260729_0017"
down_revision = "20260727_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_catalog_rank_order "
        "ON games ("
        "content_type, rank_score DESC, metrix_score DESC, "
        "is_rankable DESC, title ASC, id ASC"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_catalog_rank_order")
