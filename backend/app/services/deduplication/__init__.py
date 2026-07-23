"""Duplicate game detection, merging and consolidation.

  titles     — normalize a title/slug to a comparable key
  matching   — are two games the same title? which copy is better?
  merge      — fold a duplicate's data into the keeper
  in_memory  — dedupe a list held in memory
  store      — DB-backed detection, preview and consolidation
"""

from .in_memory import dedupe_games_in_memory
from .matching import (
    duplicate_quality_key,
    games_are_duplicates,
    total_review_count,
)
from .merge import merge_game_data
from .store import (
    consolidate_duplicate_games,
    find_duplicate_groups,
    find_existing_duplicate,
    preview_duplicate_groups,
)
from .titles import canonical_title, normalized_title

__all__ = [
    "canonical_title",
    "consolidate_duplicate_games",
    "dedupe_games_in_memory",
    "duplicate_quality_key",
    "find_duplicate_groups",
    "find_existing_duplicate",
    "games_are_duplicates",
    "merge_game_data",
    "normalized_title",
    "preview_duplicate_groups",
    "total_review_count",
]
