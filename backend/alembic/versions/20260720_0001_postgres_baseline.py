"""PostgreSQL baseline with account, SEO, and analytics tables.

Revision ID: 20260720_0001
Revises:
"""

from alembic import op

from app.database import Base
from app import models  # noqa: F401


revision = "20260720_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    columns = (
        ("games", "developer", "VARCHAR(200)"),
        ("games", "publisher", "VARCHAR(200)"),
        ("games", "playtime_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_id", "INTEGER"),
        ("games", "hltb_url", "VARCHAR(500)"),
        ("games", "hltb_main_story_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_main_extra_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_completionist_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_all_styles_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_refreshed_at", "TIMESTAMPTZ"),
        ("games", "proton_tier", "VARCHAR(16)"),
        ("games", "proton_score", "DOUBLE PRECISION"),
        ("games", "metacritic_score", "INTEGER"),
        ("games", "image_url", "VARCHAR(500)"),
        ("games", "website_url", "VARCHAR(500)"),
        ("games", "ratings_refreshed_at", "TIMESTAMPTZ"),
        ("games", "metadata_refreshed_at", "TIMESTAMPTZ"),
        ("games", "content_type", "VARCHAR(40) DEFAULT 'game'"),
        ("games", "award_count", "INTEGER DEFAULT 0"),
        ("games", "award_nominations", "INTEGER DEFAULT 0"),
        ("games", "goty_year", "INTEGER"),
        ("games", "awards", "JSON DEFAULT '[]'::json"),
        ("games", "summary_short", "TEXT"),
        ("games", "screenshots", "JSON DEFAULT '[]'::json"),
        ("games", "system_requirements", "JSON DEFAULT '[]'::json"),
        ("games", "dlcs", "JSON DEFAULT '[]'::json"),
        ("games", "similar_games", "JSON DEFAULT '[]'::json"),
        ("games", "early_access_date", "DATE"),
        ("games", "official_release_date", "DATE"),
        ("games", "rank_score", "DOUBLE PRECISION NOT NULL DEFAULT 0.0"),
        ("games", "is_rankable", "BOOLEAN NOT NULL DEFAULT false"),
        ("games", "seo_indexable", "BOOLEAN NOT NULL DEFAULT false"),
        ("games", "seo_exclusion_reason", "VARCHAR(80)"),
        ("games", "seo_updated_at", "TIMESTAMPTZ"),
        ("visit_events", "user_id", "VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL"),
        ("visit_events", "session_id_hash", "VARCHAR(64)"),
        ("visit_events", "ip_address", "VARCHAR(45)"),
        ("visit_events", "country_code", "VARCHAR(2)"),
        ("visit_events", "user_agent", "VARCHAR(500)"),
        ("visit_events", "language", "VARCHAR(35)"),
        ("visit_events", "timezone", "VARCHAR(64)"),
    )
    for table, column, column_type in columns:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")

    indexes = (
        ("ix_games_rank_score", "games", "rank_score"),
        ("ix_games_content_type", "games", "content_type"),
        ("ix_games_content_type_rank_score", "games", "content_type, rank_score DESC"),
        ("ix_games_hltb_id", "games", "hltb_id"),
        ("ix_games_seo_indexable", "games", "seo_indexable"),
        ("ix_visit_events_session_id_hash", "visit_events", "session_id_hash"),
        ("ix_visit_events_user_id", "visit_events", "user_id"),
    )
    for name, table, columns_sql in indexes:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns_sql})")


def downgrade() -> None:
    # This revision is the baseline for pre-existing production data.
    pass
