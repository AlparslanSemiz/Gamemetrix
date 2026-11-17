"""Postgres-backed failed-login counters and trusted devices.

Revision ID: 20261118_0019
Revises: 20261118_0018
"""

import sqlalchemy as sa
from alembic import op


revision = "20261118_0019"
down_revision = "20261118_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_throttle",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_login_throttle_window_start", "login_throttle", ["window_start"])
    op.create_table(
        "trusted_devices",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index("ix_trusted_devices_expires_at", "trusted_devices", ["expires_at"])


def downgrade() -> None:
    op.drop_table("trusted_devices")
    op.drop_table("login_throttle")
