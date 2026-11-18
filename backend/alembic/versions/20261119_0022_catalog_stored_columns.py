"""Store the catalog's sort/filter values as real columns.

review_count, live source count, critic presence, per-source scores and the
platform/mode tags used to be recomputed per row from JSON on every request
(jsonb_array_elements sub-queries: 6-8 s on 52k rows). They are now columns
kept current by the Game before_insert/before_update hook
(app/services/catalog_derived.py); BACKFILL_SQL fills existing rows and mirrors
that function (tests/test_catalog_derived.py compares the two).

Revision ID: 20261119_0022
Revises: 20261118_0020

NOTE: 0021 belongs to the db-saklama branch; this chain is ordered when both merge.
"""

from alembic import op


revision = "20261119_0022"
down_revision = "20261118_0020"
branch_labels = None
depends_on = None

# Literal copies of source_registry sets, frozen at this revision.
_PRIMARY = "'Metacritic','OpenCritic','IGDB','Steam'"
_CRITIC = "'Metacritic','OpenCritic'"
_PC_KEYS = "'pc','windows','microsoft windows','pc windows','steam'"

BACKFILL_SQL = f"""
WITH base AS (
    SELECT g.id,
           CASE WHEN jsonb_typeof(g.source_scores::jsonb) = 'array' THEN g.source_scores::jsonb ELSE '[]'::jsonb END AS ss,
           CASE WHEN jsonb_typeof(g.platforms::jsonb) = 'array' THEN g.platforms::jsonb ELSE '[]'::jsonb END AS pl,
           CASE WHEN jsonb_typeof(g.game_modes::jsonb) = 'array' THEN g.game_modes::jsonb ELSE '[]'::jsonb END AS gm,
           CASE WHEN jsonb_typeof(g.genres::jsonb) = 'array' THEN g.genres::jsonb ELSE '[]'::jsonb END AS ge
    FROM games g
),
names AS (
    SELECT b.id, lower(btrim(v.value #>> '{{}}')) AS n
    FROM base b, jsonb_array_elements(b.pl) AS v(value)
    WHERE jsonb_typeof(v.value) = 'string'
),
tags AS (
    SELECT id, n AS t FROM names WHERE n <> ''
    UNION
    SELECT nm.id, u.tag
    FROM names nm
    JOIN (VALUES ('playstation','playstation'), ('xbox','xbox'), ('nintendo','nintendo'),
                 ('wii','nintendo'), ('steam','steam'), ('pc','steam')) AS u(needle, tag)
      ON strpos(nm.n, u.needle) > 0
),
plat AS (
    SELECT id,
           array_agg(t ORDER BY t COLLATE "C") AS platform_tags
    FROM tags GROUP BY id
),
pcflag AS (
    SELECT DISTINCT id FROM names WHERE n IN ({_PC_KEYS})
),
modes AS (
    SELECT b.id, lower(btrim(v.value #>> '{{}}')) AS m
    FROM base b, jsonb_array_elements(b.gm) AS v(value)
    WHERE jsonb_typeof(v.value) = 'string'
),
genre_names AS (
    SELECT b.id, lower(btrim(v.value #>> '{{}}')) AS n
    FROM base b, jsonb_array_elements(b.ge) AS v(value)
    WHERE jsonb_typeof(v.value) = 'string'
),
mode_all AS (
    SELECT id, m AS t FROM modes WHERE m IN ('multiplayer','coop','singleplayer')
    UNION
    SELECT id, 'multiplayer' FROM genre_names
      WHERE n IN ('massively multiplayer','mmo','mmorpg','mmoarpg','multiplayer','pvp','online co-op')
    UNION
    SELECT id, 'coop' FROM genre_names WHERE n IN ('co-op','coop','online co-op','local co-op')
    UNION
    SELECT id, 'singleplayer' FROM genre_names WHERE n IN ('single player','singleplayer')
),
modetags AS (
    SELECT id, array_agg(t ORDER BY t COLLATE "C") AS mode_tags FROM mode_all GROUP BY id
),
rows_ AS (
    SELECT b.id,
           e.value ->> 'source' AS source,
           CASE WHEN jsonb_typeof(e.value -> 'score') = 'number' THEN (e.value ->> 'score')::float8 END AS score,
           CASE WHEN jsonb_typeof(e.value -> 'review_count') = 'number'
                THEN trunc((e.value ->> 'review_count')::numeric) END AS reviews,
           e.value ->> 'status' AS status
    FROM base b, jsonb_array_elements(b.ss) AS e(value)
    WHERE jsonb_typeof(e.value) = 'object'
),
scored AS (
    SELECT r.*,
           CASE WHEN r.reviews >= 0 AND r.reviews <= 2000000000 THEN r.reviews::bigint ELSE 0 END AS cnt,
           (r.status = 'live' AND r.score > 0 AND r.score <= 100) AS live
    FROM rows_ r
),
agg AS (
    SELECT s.id,
           sum(s.cnt) AS review_count_total,
           coalesce(sum(s.cnt) FILTER (WHERE s.live), 0) AS live_review_count,
           count(*) FILTER (WHERE s.live AND s.source IN ({_PRIMARY})
                            AND (s.source <> 'Steam' OR p.id IS NOT NULL)) AS live_primary_sources,
           coalesce(bool_or(s.live AND s.source IN ({_CRITIC})), false) AS has_live_critic,
           coalesce(max(s.score) FILTER (WHERE s.live AND s.source = 'Steam'), 0) AS steam_score,
           coalesce(max(s.score) FILTER (WHERE s.live AND s.source = 'OpenCritic'), 0) AS opencritic_score,
           coalesce(max(s.score) FILTER (WHERE s.live AND s.source = 'Metacritic'), 0) AS metacritic_live_score
    FROM scored s LEFT JOIN pcflag p ON p.id = s.id
    GROUP BY s.id
)
UPDATE games g SET
    review_count_total = coalesce(a.review_count_total, 0),
    live_review_count = coalesce(a.live_review_count, 0),
    live_primary_sources = coalesce(a.live_primary_sources, 0),
    has_live_critic = coalesce(a.has_live_critic, false),
    steam_score = coalesce(a.steam_score, 0),
    opencritic_score = coalesce(a.opencritic_score, 0),
    metacritic_live_score = coalesce(a.metacritic_live_score, 0),
    platform_tags = coalesce(pt.platform_tags, ARRAY[]::text[]),
    mode_tags = coalesce(mt.mode_tags, ARRAY[]::text[])
FROM base b
LEFT JOIN agg a ON a.id = b.id
LEFT JOIN plat pt ON pt.id = b.id
LEFT JOIN modetags mt ON mt.id = b.id
WHERE g.id = b.id
"""

_COLUMNS = (
    ("review_count_total", "bigint NOT NULL DEFAULT 0"),
    ("live_review_count", "bigint NOT NULL DEFAULT 0"),
    ("live_primary_sources", "smallint NOT NULL DEFAULT 0"),
    ("has_live_critic", "boolean NOT NULL DEFAULT false"),
    ("steam_score", "double precision NOT NULL DEFAULT 0"),
    ("opencritic_score", "double precision NOT NULL DEFAULT 0"),
    ("metacritic_live_score", "double precision NOT NULL DEFAULT 0"),
    ("platform_tags", "text[] NOT NULL DEFAULT '{}'"),
    ("mode_tags", "text[] NOT NULL DEFAULT '{}'"),
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_games_type_review_count_total ON games (content_type, review_count_total DESC)",
    "CREATE INDEX IF NOT EXISTS ix_games_type_live_primary_sources ON games (content_type, live_primary_sources)",
    "CREATE INDEX IF NOT EXISTS ix_games_live_critic ON games (content_type, rank_score DESC) WHERE has_live_critic",
    "CREATE INDEX IF NOT EXISTS ix_games_platform_tags_gin ON games USING gin (platform_tags)",
    "CREATE INDEX IF NOT EXISTS ix_games_mode_tags_gin ON games USING gin (mode_tags)",
)


def upgrade() -> None:
    for name, definition in _COLUMNS:
        op.execute(f"ALTER TABLE games ADD COLUMN IF NOT EXISTS {name} {definition}")
    op.execute(BACKFILL_SQL)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute("ANALYZE games")


def downgrade() -> None:
    for name in (
        "ix_games_mode_tags_gin",
        "ix_games_platform_tags_gin",
        "ix_games_live_critic",
        "ix_games_type_live_primary_sources",
        "ix_games_type_review_count_total",
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for name, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE games DROP COLUMN IF EXISTS {name}")
