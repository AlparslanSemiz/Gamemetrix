"""RAWG catalog import and per-game metadata enrichment.

Note: unlike a pure integration client, this package reaches up into
`services.rawg_import` / `services.deduplication` for its Game-building and merge
logic — an intentional, long-standing exception kept from the original module.

  matching        — is this RAWG result the game we asked for?
  client          — endpoint constants + budget-gated GET
  persistence     — ExternalId upserts + response snapshots
  catalog_import  — bulk paging import
  detail          — per-game enrichment
"""

from .catalog_import import (
    import_catalog_to_size,
    import_rawg_games,
    import_rawg_nintendo_games,
)
from .detail import enrich_rawg_game_detail

__all__ = [
    "enrich_rawg_game_detail",
    "import_catalog_to_size",
    "import_rawg_games",
    "import_rawg_nintendo_games",
]
