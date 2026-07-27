"""Track when games enter the catalog for admin growth reporting.

Revision ID: 20260727_0013
Revises: 20260725_0012
"""

from alembic import op


revision = "20260727_0013"
down_revision = "20260725_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE games ADD COLUMN IF NOT EXISTS catalog_added_at TIMESTAMPTZ"
    )
    # Existing games predate this field. The earliest source identity is the
    # closest durable proxy for when a row first entered GameMetrix. Rows with no
    # source identity remain null rather than receiving a misleading timestamp.
    op.execute(
        """
        UPDATE games AS game
        SET catalog_added_at = source.first_seen
        FROM (
            SELECT game_id, MIN(created_at) AS first_seen
            FROM external_ids
            GROUP BY game_id
        ) AS source
        WHERE game.id = source.game_id
          AND game.catalog_added_at IS NULL
        """
    )
    op.execute(
        "ALTER TABLE games ALTER COLUMN catalog_added_at SET DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_content_type_catalog_added_at "
        "ON games (content_type, catalog_added_at) "
        "WHERE catalog_added_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_games_content_type_catalog_added_at")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS catalog_added_at")
