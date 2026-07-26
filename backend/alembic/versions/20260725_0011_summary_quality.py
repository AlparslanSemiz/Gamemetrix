"""Description-quality audit fields.

  - summary_checked_at — orders the description audit rotation. Separate from
    summary_refreshed_at, which from now on moves only when the text changed.
  - summary_quality    — last audit verdict (ok / cleaned / unusable).

Revision ID: 20260725_0011
Revises: 20260725_0010
"""

from alembic import op


revision = "20260725_0011"
down_revision = "20260725_0010"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("games", "summary_checked_at", "TIMESTAMPTZ"),
    ("games", "summary_quality", "VARCHAR(20)"),
)

_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_games_summary_checked_at", "games", "summary_checked_at"),
    ("ix_games_summary_quality", "games", "summary_quality"),
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
