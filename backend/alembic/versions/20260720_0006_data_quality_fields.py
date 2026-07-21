"""Data-quality automation fields.

Adds columns that drive periodic self-healing of the catalog:
  - is_endless / endless_checked_at — endless (roguelike/MMO/sandbox) playtime flag.
  - data_complete — "fully populated, skip in the refresh rotation" gate.
  - franchise — accurate series key from IGDB franchise/collection.
  - summary_refreshed_at — orders periodic re-summarization.

Revision ID: 20260720_0006
Revises: 20260720_0005
"""

from alembic import op


revision = "20260720_0006"
down_revision = "20260720_0005"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("games", "summary_refreshed_at", "TIMESTAMPTZ"),
    ("games", "data_complete", "BOOLEAN NOT NULL DEFAULT false"),
    ("games", "is_endless", "BOOLEAN NOT NULL DEFAULT false"),
    ("games", "endless_checked_at", "TIMESTAMPTZ"),
    ("games", "franchise", "VARCHAR(200)"),
)

_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_games_data_complete", "games", "data_complete"),
    ("ix_games_franchise", "games", "franchise"),
)


def upgrade() -> None:
    for table, column, column_type in _COLUMNS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")
    for name, table, columns_sql in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns_sql})")


def downgrade() -> None:
    for name, _table, _columns_sql in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for table, column, _column_type in _COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
