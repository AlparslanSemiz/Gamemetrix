"""HowLongToBeat playtime enrichment.

  matching — similarity scoring and the HltbMatch record
  client   — runtime endpoint/token discovery + search
  backfill — applying matches to games and sweeping the catalog
"""

from .backfill import apply_hltb_match, backfill_hltb_playtimes, repair_missing_cover
from .client import HltbClient
from .matching import HltbMatch

__all__ = [
    "HltbClient",
    "HltbMatch",
    "apply_hltb_match",
    "backfill_hltb_playtimes",
    "repair_missing_cover",
]
