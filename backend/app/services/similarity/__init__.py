""""Games like X" similarity ranking.

Server-side port of the algorithm that used to live in the frontend
(GameDetailPage.tsx). Moving it here lets a single round of DB queries supply
candidates instead of the frontend firing 5-6 separate /api/games requests and
re-scoring hundreds of games in the browser on every page load.

Layering: taxonomy (vocabulary) → signals (one game) → profiles (two games)
→ scoring / gates → ranking → queries.
"""

from .ai_rerank import rerank_with_ai
from .cache import cached_series_slugs, cached_similar_slugs, clear_similarity_cache
from .gates import passes_similarity_gate
from .queries import find_series_games, find_similar_games, games_by_slugs
from .ranking import rank_similar_games
from .scoring import similarity_score
from .signals import series_key_for_title

__all__ = [
    "cached_series_slugs",
    "cached_similar_slugs",
    "clear_similarity_cache",
    "find_series_games",
    "find_similar_games",
    "games_by_slugs",
    "passes_similarity_gate",
    "rank_similar_games",
    "rerank_with_ai",
    "series_key_for_title",
    "similarity_score",
]
