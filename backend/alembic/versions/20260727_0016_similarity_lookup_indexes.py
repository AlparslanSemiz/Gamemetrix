"""Indexes for the "games like X" candidate queries.

Every candidate query used a predicate no index could serve, so each one scanned
the whole games table. Measured on a 52k-row catalog before/after:

  genre "FPS"  (JSON array expanded per row)   14784ms ->  261ms
  series title (ILIKE '%baldur%s%gate%')       69739ms ->   84ms
  developer    (unindexed equality)            13283ms ->   37ms

The genre index covers the `genres::jsonb` cast expression, so it only applies to
containment (`@>`) — see `services/similarity/queries.py`.

Revision ID: 20260727_0016
Revises: 20260727_0015
"""

from alembic import op


revision = "20260727_0016"
down_revision = "20260727_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_title_trgm"
        " ON games USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_summary_short_trgm"
        " ON games USING gin (summary_short gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_genres_gin"
        " ON games USING gin ((genres::jsonb) jsonb_path_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_games_developer ON games (developer)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_developer")
    op.execute("DROP INDEX IF EXISTS ix_games_genres_gin")
    op.execute("DROP INDEX IF EXISTS ix_games_summary_short_trgm")
    op.execute("DROP INDEX IF EXISTS ix_games_title_trgm")
