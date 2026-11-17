"""Verified Steam ids, slug redirects, ProtonDB freshness and normalized title search.

Revision ID: 20260730_0018
Revises: 20260729_0017
"""

import sqlalchemy as sa
from alembic import op


revision = "20260730_0018"
down_revision = "20260729_0017"
branch_labels = None
depends_on = None

# alias -> catalog title it stands for. Resolved by normalized title at migration time;
# aliases whose game is not in this catalog are skipped.
_ALIASES: dict[str, str] = {
    "gta v": "grand theft auto v",
    "gta 5": "grand theft auto v",
    "gta5": "grand theft auto v",
    "gtav": "grand theft auto v",
    "gta iv": "grand theft auto iv",
    "gta 4": "grand theft auto iv",
    "bg3": "baldurs gate 3",
    "rdr2": "red dead redemption 2",
    "rdr": "red dead redemption",
    "tlou": "the last of us",
    "tlou2": "the last of us part ii",
    "kcd": "kingdom come deliverance",
    "kcd2": "kingdom come deliverance ii",
    "cs2": "counter strike 2",
    "csgo": "counter strike global offensive",
    "cs go": "counter strike global offensive",
    "botw": "the legend of zelda breath of the wild",
    "totk": "the legend of zelda tears of the kingdom",
    "tw3": "the witcher 3 wild hunt",
    "witcher 3": "the witcher 3 wild hunt",
    "cp2077": "cyberpunk 2077",
    "dos2": "divinity original sin 2",
    "mhw": "monster hunter world",
    "gow": "god of war",
    "re4": "resident evil 4",
    "ds3": "dark souls iii",
    "nms": "no mans sky",
    "sts": "slay the spire",
    "l4d2": "left 4 dead 2",
    "hl2": "half life 2",
    "hk": "hollow knight",
    "tf2": "team fortress 2",
    "ow2": "overwatch 2",
    "mc": "minecraft",
    "ac odyssey": "assassins creed odyssey",
}

# SQL twin of app.search_text.normalize_search_text.
_NORMALIZE_SQL = (
    "btrim(regexp_replace("
    "regexp_replace(lower(unaccent(title)), '[''’‘`´]', '', 'g'), "
    "'[^[:alnum:]]+', ' ', 'g'))"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.add_column("games", sa.Column("title_normalized", sa.Text(), nullable=False, server_default=""))
    op.add_column("games", sa.Column("steam_app_id_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("games", sa.Column("proton_refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(f"UPDATE games SET title_normalized = {_NORMALIZE_SQL}")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_games_title_normalized_trgm "
        "ON games USING gin (title_normalized gin_trgm_ops)"
    )

    op.create_table(
        "slug_redirects",
        sa.Column("old_slug", sa.String(180), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_slug_redirects_game_id", "slug_redirects", ["game_id"])

    op.create_table(
        "game_search_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alias", sa.String(80), nullable=False),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_game_search_aliases_alias", "game_search_aliases", ["alias"])
    op.create_index("ix_game_search_aliases_game_id", "game_search_aliases", ["game_id"])

    connection = op.get_bind()
    for alias, normalized_title in _ALIASES.items():
        connection.execute(
            sa.text(
                "INSERT INTO game_search_aliases (alias, game_id) "
                "SELECT :alias, id FROM games WHERE title_normalized = :title "
                "AND content_type = 'game' ORDER BY rank_score DESC, id ASC LIMIT 1"
            ),
            {"alias": alias, "title": normalized_title},
        )


def downgrade() -> None:
    op.drop_table("game_search_aliases")
    op.drop_table("slug_redirects")
    op.execute("DROP INDEX IF EXISTS ix_games_title_normalized_trgm")
    op.drop_column("games", "proton_refreshed_at")
    op.drop_column("games", "steam_app_id_verified_at")
    op.drop_column("games", "title_normalized")
