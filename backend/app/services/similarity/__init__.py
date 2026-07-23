""""Games like X" similarity ranking.

Server-side port of the algorithm that used to live in the frontend
(GameDetailPage.tsx). Moving it here lets a single round of DB queries supply
candidates instead of the frontend firing 5-6 separate /api/games requests and
re-scoring hundreds of games in the browser on every page load.

Layering: taxonomy (vocabulary) → signals (one game) → profiles (two games)
→ scoring / gates → ranking → queries.
"""

from .gates import passes_similarity_gate
from .queries import find_series_games, find_similar_games
from .ranking import rank_similar_games
from .scoring import similarity_score
from .signals import series_key_for_title

__all__ = [
    "find_series_games",
    "find_similar_games",
    "passes_similarity_gate",
    "rank_similar_games",
    "series_key_for_title",
    "similarity_score",
]
