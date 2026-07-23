"""Scoring weights, source orderings and cache lifetimes.

`SOURCE_WEIGHTS` is deliberately a plain mutable dict: `routers/ratings.py`
rewrites entries at runtime to retune weights without a redeploy, and every
reader binds this same object so in-place edits take effect immediately.

Membership-only source sets are re-exported from `source_registry`, the single
source of truth (invariant I-4). `SCORE_PRIMARIES` stays an explicit ordered
tuple: it drives the summation order in `calculate_metrix_score`, so a set would
make float accumulation order non-deterministic.
"""

from datetime import timedelta

from ..source_registry import (
    CRITIC_SOURCES,
    RATING_SOURCES,
    REGISTRY,
    USER_RATING_SOURCES as REGISTRY_USER_RATING_SOURCES,
)

# Editorial weight per source, seeded from source_registry — the single source of
# truth (invariant I-4). Non-rating sources carry 0.0 there, which is what keeps
# them out of the score. Changing a value alters published scores (AI_Guidelines §10).
SOURCE_WEIGHTS: dict[str, float] = {
    key: definition.weight for key, definition in REGISTRY.items()
}

SOURCE_ORDER: dict[str, int] = {
    "Metacritic": 0,
    "OpenCritic": 1,
    "IGDB": 2,
    "Steam": 3,
    "RAWG": 4,
    "SteamSpy": 5,
    "CheapShark": 6,
    "FreeToGame": 7,
}

# Four named primary slots. RAWG and support sources never enter the score.
SCORE_PRIMARIES = ("Metacritic", "OpenCritic", "Steam", "IGDB")
SCORE_BASELINE = 70.0

CRITIC_RATING_SOURCES = CRITIC_SOURCES
USER_RATING_SOURCES = REGISTRY_USER_RATING_SOURCES
RATING_SRC = RATING_SOURCES

CACHE_TTL = timedelta(hours=24)
# Fully-populated games only need an occasional re-verify, so they stop competing
# with the incomplete tail for daily API budget.
DATA_COMPLETE_TTL = timedelta(days=30)
RAWG_CACHE_TTL = timedelta(days=30)

DEFAULT_SOURCE_WEIGHT = 0.05
UNRANKED_SOURCE_ORDER = 99
EARLIEST_MEANINGFUL_YEAR = 1970
