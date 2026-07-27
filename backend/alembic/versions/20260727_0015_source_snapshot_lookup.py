"""Index source snapshots used as provider negative-result cache.

Revision ID: 20260727_0015
Revises: 20260727_0014
"""

from alembic import op


revision = "20260727_0015"
down_revision = "20260727_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_source_snapshots_lookup",
        "source_snapshots",
        ["source", "endpoint", "external_id", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_snapshots_lookup", table_name="source_snapshots")
