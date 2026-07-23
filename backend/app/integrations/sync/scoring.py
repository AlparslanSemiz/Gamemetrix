"""The GameMetrix score: a reliability-adjusted weighted average of the primaries.

Sparse source coverage shrinks high scores toward a neutral baseline and applies
a small uncertainty penalty, so a 95 from one source cannot rank like a 95 from
four. Every constant here is a published-score input — see AI_Guidelines §10.
"""

from ...config import get_settings
from .constants import (
    CRITIC_RATING_SOURCES,
    DEFAULT_SOURCE_WEIGHT,
    RATING_SRC,
    SCORE_BASELINE,
    SCORE_PRIMARIES,
    SOURCE_WEIGHTS,
    USER_RATING_SOURCES,
)
from .values import review_count, score_value

_UNCERTAINTY_PENALTY_SCALE = 6.0
_MIN_RELIABILITY = 0.46

# primary_count -> (coverage_factor, max_reliability). Index 0 covers "none".
_COVERAGE_BY_PRIMARY_COUNT: tuple[tuple[float, float], ...] = (
    (0.40, 0.46),
    (0.62, 0.68),
    (0.78, 0.84),
    (0.90, 0.94),
    (1.00, 1.00),
)

_BALANCE_BOTH = 0.03
_BALANCE_CRITIC_ONLY = -0.04
_BALANCE_USER_ONLY = -0.06
_BALANCE_NEITHER = -0.10

# Descending review-count thresholds -> adjustment.
_VOLUME_THRESHOLDS: tuple[tuple[int, float], ...] = (
    (100_000, 0.04),
    (10_000, 0.02),
    (500, 0.01),
)
_VOLUME_NONE = -0.04
_VOLUME_LOW = -0.02


def calculate_metrix_score(source_scores: list[dict[str, object]]) -> float:
    """
    Reliability-adjusted weighted average of the four primary sources.

    Admin weights provide the editorial baseline and SCORE_WEIGHT_<SOURCE> env
    values act as relative deployment-level multipliers.
    """
    weights = _effective_weights()
    live = {
        str(s.get("source")): value
        for s in source_scores
        if s.get("status") == "live" and (value := score_value(s)) is not None
    }
    selected = [(src, live[src]) for src in SCORE_PRIMARIES if src in live]
    if not selected:
        return 0.0

    total_weight = sum(weights.get(src, 1.0) for src, _ in selected)
    if total_weight == 0:
        return 0.0

    raw_score = sum(weights.get(src, 1.0) * score for src, score in selected) / total_weight
    reliability = _score_reliability_factor(source_scores, selected)
    uncertainty_penalty = (1.0 - reliability) * _UNCERTAINTY_PENALTY_SCALE
    adjusted = (raw_score * reliability) + (SCORE_BASELINE * (1.0 - reliability)) - uncertainty_penalty
    return round(max(0.0, min(100.0, adjusted)), 1)


def _effective_weights() -> dict[str, float]:
    cfg = get_settings()
    modifiers = {
        "Metacritic": cfg.SCORE_WEIGHT_METACRITIC,
        "OpenCritic": cfg.SCORE_WEIGHT_OPENCRITIC,
        "Steam": cfg.SCORE_WEIGHT_STEAM,
        "IGDB": cfg.SCORE_WEIGHT_IGDB,
    }
    return {
        source: max(0.0, SOURCE_WEIGHTS[source] * modifiers[source])
        for source in SCORE_PRIMARIES
    }


def _score_reliability_factor(
    source_scores: list[dict[str, object]],
    selected: list[tuple[str, float]],
) -> float:
    selected_sources = {source for source, _ in selected}
    primary_count = len(selected_sources & set(SCORE_PRIMARIES))
    total_reviews = sum(
        review_count(s)
        for s in source_scores
        if s.get("status") == "live" and str(s.get("source")) in RATING_SRC
    )

    coverage_factor, max_reliability = _COVERAGE_BY_PRIMARY_COUNT[
        min(primary_count, len(_COVERAGE_BY_PRIMARY_COUNT) - 1)
    ]
    balance_adjust = _balance_adjust(selected_sources)
    volume_adjust = _volume_adjust(total_reviews)
    return max(_MIN_RELIABILITY, min(max_reliability, coverage_factor + balance_adjust + volume_adjust))


def _balance_adjust(selected_sources: set[str]) -> float:
    has_critic = bool(selected_sources & CRITIC_RATING_SOURCES)
    has_user = bool(selected_sources & USER_RATING_SOURCES)
    if has_critic and has_user:
        return _BALANCE_BOTH
    if has_critic:
        return _BALANCE_CRITIC_ONLY
    if has_user:
        return _BALANCE_USER_ONLY
    return _BALANCE_NEITHER


def _volume_adjust(total_reviews: int) -> float:
    for threshold, adjustment in _VOLUME_THRESHOLDS:
        if total_reviews >= threshold:
            return adjustment
    return _VOLUME_NONE if total_reviews == 0 else _VOLUME_LOW


def weighted_source_average(
    source_scores: list[dict[str, object]],
    sources: frozenset[str] | set[str],
) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for s in source_scores:
        source = str(s.get("source", ""))
        if source not in sources:
            continue
        score = score_value(s)
        if s.get("status") != "live" or score is None:
            continue
        weight = SOURCE_WEIGHTS.get(source, DEFAULT_SOURCE_WEIGHT)
        weighted_total += score * weight
        total_weight += weight
    return round(weighted_total / total_weight, 1) if total_weight else 0.0
