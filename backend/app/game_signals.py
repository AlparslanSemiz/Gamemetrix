"""Rating-signal classification derived from a game's stored source scores.

Pure functions over the `source_scores` JSON list and a game's applicable
primary sources — no ORM, no I/O — so the tiers can be reasoned about and tested
in isolation. `Game`'s display properties are thin delegators to these.
"""

from math import isfinite

from .integrations.source_registry import CRITIC_SOURCES, RATING_SOURCES, USER_RATING_SOURCES

# Confidence-level review-count thresholds
STRONG_MIN_REVIEWS = 500
SOLID_MIN_REVIEWS = 100
SOLID_CRITIC_MIN_REVIEWS = 50
LIMITED_MIN_REVIEWS = 1
STRONG_MIN_SOURCES = 3
SOLID_MIN_SOURCES = 2

# Popularity label thresholds (total review count)
POPULARITY_PHENOMENON = 500_000
POPULARITY_VERY_HIGH = 100_000
POPULARITY_HIGH = 25_000
POPULARITY_MEDIUM = 5_000
POPULARITY_LOW = 500

_MAX_REVIEW_COUNT = 2_000_000_000

_DATA_STRENGTH_BY_CONFIDENCE = {
    "Strong": "DATA_STRONG",
    "Solid": "DATA_SOLID",
    "Limited": "DATA_LIMITED",
    "Catalog": "CATALOG_ONLY",
}
_POPULARITY_TIERS: tuple[tuple[int, str], ...] = (
    (POPULARITY_PHENOMENON, "Phenomenon"),
    (POPULARITY_VERY_HIGH, "Very High"),
    (POPULARITY_HIGH, "High"),
    (POPULARITY_MEDIUM, "Medium"),
    (POPULARITY_LOW, "Niche"),
)

SourceScores = list[dict[str, str | float | int]] | None


def valid_score(row: object) -> bool:
    if not isinstance(row, dict) or row.get("status") != "live":
        return False
    try:
        value = float(row.get("score", 0) or 0)
    except (TypeError, ValueError):
        return False
    return isfinite(value) and 0 < value <= 100


def safe_review_count(row: object) -> int:
    if not isinstance(row, dict):
        return 0
    try:
        value = int(row.get("review_count", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return value if 0 <= value <= _MAX_REVIEW_COUNT else 0


def _live_rating_rows(source_scores: SourceScores) -> list[dict]:
    return [
        row
        for row in (source_scores or [])
        if isinstance(row, dict) and valid_score(row) and str(row.get("source")) in RATING_SOURCES
    ]


def _live_rating_sources(source_scores: SourceScores) -> set[str]:
    return {str(row.get("source")) for row in _live_rating_rows(source_scores)}


def live_primary_source_count(source_scores: SourceScores, applicable: frozenset[str]) -> int:
    return sum(
        1
        for row in (source_scores or [])
        if isinstance(row, dict) and row.get("source") in applicable and valid_score(row)
    )


def confidence_level(source_scores: SourceScores, applicable: frozenset[str]) -> str:
    rows = _live_rating_rows(source_scores)
    live_sources = {str(row.get("source")) for row in rows}
    live_primary = live_sources & applicable
    live_critic = live_primary & CRITIC_SOURCES
    live_user = live_primary & (applicable & USER_RATING_SOURCES)
    total_reviews = sum(safe_review_count(row) for row in rows)

    if (
        len(live_primary) >= min(STRONG_MIN_SOURCES, len(applicable))
        and live_critic
        and live_user
        and total_reviews >= STRONG_MIN_REVIEWS
    ):
        return "Strong"
    if live_critic and live_user and len(live_primary) >= SOLID_MIN_SOURCES and total_reviews >= SOLID_MIN_REVIEWS:
        return "Solid"
    if len(live_critic) >= SOLID_MIN_SOURCES and total_reviews >= SOLID_CRITIC_MIN_REVIEWS:
        return "Solid"
    if len(live_primary) >= STRONG_MIN_SOURCES:
        return "Solid"
    if live_primary and total_reviews >= LIMITED_MIN_REVIEWS:
        return "Limited"
    if "RAWG" in live_sources:
        return "Limited"
    return "Catalog"


def data_strength(level: str) -> str:
    return _DATA_STRENGTH_BY_CONFIDENCE.get(level, "CATALOG_ONLY")


def score_profile(source_scores: SourceScores) -> str:
    live_sources = _live_rating_sources(source_scores)
    has_critic = bool(live_sources & CRITIC_SOURCES)
    has_user = bool(live_sources & USER_RATING_SOURCES)
    if has_critic and has_user:
        return "critic + user"
    if has_critic:
        return "critic-heavy"
    if has_user:
        return "user-heavy"
    return "sparse"


def popularity_label(source_scores: SourceScores) -> str | None:
    total_reviews = sum(safe_review_count(row) for row in _live_rating_rows(source_scores))
    for threshold, label in _POPULARITY_TIERS:
        if total_reviews >= threshold:
            return label
    return None
