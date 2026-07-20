"""Admin audit trail: every /admin/* request and login attempt.

Revision ID: 20260720_0003
Revises: 20260720_0002
"""

import sqlalchemy as sa
from alembic import op


revision = "20260720_0003"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded like every other migration here because 20260720_0001 runs
    # Base.metadata.create_all against live metadata: the baseline is not frozen
    # in time, so on a database it adopts it already creates every table models.py
    # defines today, this one included.
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    for column in ("username", "action", "path", "status_code", "success", "created_at"):
        op.create_index(
            f"ix_admin_audit_logs_{column}",
            "admin_audit_logs",
            [column],
            if_not_exists=True,
        )


def downgrade() -> None:
    op.drop_table("admin_audit_logs")
