"""Indexes used by external-catalog identity matching.

Revision ID: 20260725_0010
Revises: 20260724_0009
"""

from alembic import op


revision = "20260725_0010"
down_revision = "20260724_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_lower_title ON games (lower(title))"
    )
    op.create_index(
        "ix_external_ids_source_external_id",
        "external_ids",
        ["source", "external_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_external_ids_game_source",
        "external_ids",
        ["game_id", "source"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_ids_game_source",
        table_name="external_ids",
        if_exists=True,
    )
    op.drop_index(
        "ix_external_ids_source_external_id",
        table_name="external_ids",
        if_exists=True,
    )
    op.execute("DROP INDEX IF EXISTS ix_games_lower_title")
