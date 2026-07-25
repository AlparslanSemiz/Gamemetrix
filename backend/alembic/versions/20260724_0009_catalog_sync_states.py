"""Durable cursors for resumable catalog imports.

Revision ID: 20260724_0009
Revises: 20260724_0008
"""

import sqlalchemy as sa
from alembic import op


revision = "20260724_0009"
down_revision = "20260724_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_sync_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("cursor", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_catalog_sync_states_source",
        "catalog_sync_states",
        ["source"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_sync_states_source", table_name="catalog_sync_states")
    op.drop_table("catalog_sync_states")
