"""Periodic background job heartbeats.

One row per periodic loop, upserted each cycle, so the admin panel can show
each job's last run, next due time, and what that run fetched.

Revision ID: 20260724_0007
Revises: 20260720_0006
"""

import sqlalchemy as sa
from alembic import op


revision = "20260724_0007"
down_revision = "20260720_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded like 20260720_0003: the baseline migration runs
    # Base.metadata.create_all against live metadata, so a database first
    # migrated after this model existed already has the table.
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        if_not_exists=True,
    )
    op.create_index(
        "ix_job_runs_job",
        "job_runs",
        ["job"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_job", table_name="job_runs")
    op.drop_table("job_runs")
