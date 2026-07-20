"""Move hardcoded per-game data out of source and into the database.

Adds games.steam_app_id, then seeds it from the literals that used to live in
integrations/steam.py. Also applies, once, the cover corrections that
main.py::_repair_known_media re-applied on every startup (overwriting whatever
an admin or importer had set) and the manual patches from hltb.py's
KNOWN_COVER_URLS. After this migration those literals are deleted from the code.

Revision ID: 20260720_0005
Revises: 20260720_0004
"""

import sqlalchemy as sa
from alembic import op


revision = "20260720_0005"
down_revision = "20260720_0004"
branch_labels = None
depends_on = None


# slug -> Steam App ID (formerly steam.STEAM_APP_IDS)
_STEAM_APP_IDS: dict[str, int] = {
    "baldurs-gate-3": 1086940,
    "elden-ring": 1245620,
    "hades": 1145360,
    "disco-elysium-the-final-cut": 632470,
    "hi-fi-rush": 1817230,
    "red-dead-redemption-2": 1174180,
    "resident-evil-4-remake": 2050650,
    "resident-evil-4": 254700,
    "resident-evil-2-remake": 883710,
    "resident-evil-village": 1196590,
    "sekiro-shadows-die-twice": 814380,
    "dark-souls-3": 374320,
    "cyberpunk-2077": 1091500,
    "god-of-war-2018": 1593500,
    "god-of-war-ragnarok": 2322010,
    "the-last-of-us-part-2": 2531310,
    "the-last-of-us-part-ii-remastered": 2531310,
}

_STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps"

# slug -> cover URL (formerly main._repair_known_media + hltb.KNOWN_COVER_URLS)
_COVER_CORRECTIONS: dict[str, str] = {
    "disco-elysium-the-final-cut": f"{_STEAM_CDN}/632470/capsule_616x353.jpg",
    "resident-evil-4-remake": f"{_STEAM_CDN}/2050650/capsule_616x353.jpg",
    "resident-evil-4": f"{_STEAM_CDN}/254700/library_hero.jpg",
    "the-last-of-us-part-2": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2531310/header.jpg",
    "the-last-of-us-part-ii-remastered": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2531310/header.jpg",
    "the-witcher-goodies-collection-709179": "https://images.gog-statics.com/a344e6ee3a17af9e6529dd22deda462aa0c5cc7a856d3a4f8cb84e15d31a3a76.jpg",
    "rock-band-music-store-28624": "https://cdn2.steamgriddb.com/grid/a1d2282208205a6832a37601df840de2.png",
    "ea-play-hub-481920": "https://image.api.playstation.com/gs2-sec/appkgo/prod/CUSA16175_00/2/i_06a73a7513560fbfe586ab17d2a66df2c1bfec61431138c6cc60a07841dd6d2b/i/pic0.png?thumb=true&w=512",
    "last-fm-28854": "https://upload.wikimedia.org/wikipedia/commons/c/c4/Lastfm_logo.svg",
    "into-the-war-20690": "https://howlongtobeat.com/games/Into_The_War_header.jpg",
}


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS steam_app_id INTEGER")
    op.create_index("ix_games_steam_app_id", "games", ["steam_app_id"], if_not_exists=True)

    connection = op.get_bind()
    for slug, app_id in _STEAM_APP_IDS.items():
        connection.execute(
            sa.text(
                "UPDATE games SET steam_app_id = :app_id "
                "WHERE slug = :slug AND steam_app_id IS NULL"
            ),
            {"app_id": app_id, "slug": slug},
        )

    # Only fills gaps: an operator who has since set a better cover keeps it.
    for slug, cover_url in _COVER_CORRECTIONS.items():
        connection.execute(
            sa.text(
                "UPDATE games SET cover_url = :url, image_url = :url "
                "WHERE slug = :slug "
                "AND (cover_url IS NULL OR trim(cover_url) = '' "
                "     OR lower(cover_url) IN ('none', 'null'))"
            ),
            {"url": cover_url, "slug": slug},
        )


def downgrade() -> None:
    op.drop_index("ix_games_steam_app_id", table_name="games", if_exists=True)
    op.drop_column("games", "steam_app_id")
