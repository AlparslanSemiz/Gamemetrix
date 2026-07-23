"""Scoring engine and game refresh orchestration.

  constants     — weights, source orderings, cache lifetimes
  values        — safe numeric reads off a stored score row
  serialization — ExternalScore <-> stored row, and merging
  scoring       — calculate_metrix_score + reliability model
  cache         — freshness checks and cached-score reuse
  fetching      — per-source fetch plan and budget gating
  ranking       — rankability and derived display scores
  persistence   — rating/source snapshots and external IDs
  refresh       — the end-to-end refresh entry point

`SOURCE_WEIGHTS` is re-exported as the same mutable dict that `constants` owns,
so runtime retuning via `routers/ratings.py` reaches the scorer.
"""

from .cache import cached_score, game_needs_rating_refresh
from .constants import (
    CACHE_TTL,
    CRITIC_RATING_SOURCES,
    DATA_COMPLETE_TTL,
    RAWG_CACHE_TTL,
    SOURCE_ORDER,
    SOURCE_WEIGHTS,
    USER_RATING_SOURCES,
)
from .persistence import backfill_current_source_records, persist_source_records
from .ranking import compute_rank_fields, update_derived_scores
from .refresh import refresh_game_sources
from .scoring import calculate_metrix_score, weighted_source_average
from .serialization import merge_source_scores, score_to_dict
from .values import review_count, score_value

__all__ = [
    "CACHE_TTL",
    "CRITIC_RATING_SOURCES",
    "DATA_COMPLETE_TTL",
    "RAWG_CACHE_TTL",
    "SOURCE_ORDER",
    "SOURCE_WEIGHTS",
    "USER_RATING_SOURCES",
    "backfill_current_source_records",
    "cached_score",
    "calculate_metrix_score",
    "compute_rank_fields",
    "game_needs_rating_refresh",
    "merge_source_scores",
    "persist_source_records",
    "refresh_game_sources",
    "review_count",
    "score_to_dict",
    "score_value",
    "update_derived_scores",
    "weighted_source_average",
]
