"""Persistent Groq-backed catalog quality review state.

Revision ID: 20260724_0008
Revises: 20260724_0007
"""

import sqlalchemy as sa
from alembic import op


revision = "20260724_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_quality_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_catalog_quality_reviews_game_id",
        "catalog_quality_reviews",
        ["game_id"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        "ix_catalog_quality_reviews_status",
        "catalog_quality_reviews",
        ["status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_catalog_quality_reviews_checked_at",
        "catalog_quality_reviews",
        ["checked_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_quality_reviews_checked_at", table_name="catalog_quality_reviews")
    op.drop_index("ix_catalog_quality_reviews_status", table_name="catalog_quality_reviews")
    op.drop_index("ix_catalog_quality_reviews_game_id", table_name="catalog_quality_reviews")
    op.drop_table("catalog_quality_reviews")
