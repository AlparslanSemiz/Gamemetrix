"""Per-day token budgets alongside the request budgets.

LLM providers run out of tokens long before they run out of requests: Groq's
free gpt-oss-20b allows 1,000 requests but only 200,000 tokens a day, and our
catalog prompts exhaust the tokens first. Counting requests alone therefore
either wastes most of the allowance or overshoots it.

Revision ID: 20260725_0012
Revises: 20260725_0011
"""

from alembic import op


revision = "20260725_0012"
down_revision = "20260725_0011"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("api_request_budgets", "token_count", "INTEGER NOT NULL DEFAULT 0"),
    ("api_request_budgets", "token_limit", "INTEGER NOT NULL DEFAULT 0"),
)


def upgrade() -> None:
    for table, column, column_type in _COLUMNS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")


def downgrade() -> None:
    for table, column, _column_type in _COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
