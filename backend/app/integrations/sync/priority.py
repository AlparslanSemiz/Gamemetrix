"""Which stale games get the scarce rating budget first, and which refreshes count.

Budgets cannot cover the whole catalog every cycle, so the order decides who stays
unrated. Priority = popularity x release recency x missing primary sources x
staleness; a freshly released big game with no score yet therefore outranks an old
game that only needs a re-check.
"""

import heapq
import math
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime

from ...models import Game
from ...game_signals import safe_review_count
from ..types import ExternalScore
from .cache import game_needs_rating_refresh
from .values import score_value

# A refresh that only hit these walls did not actually ask the provider anything.
_NOT_A_PROVIDER_ANSWER = (
    "not configured",
    "budget",
    "rate limit",
    "rate_limited",
    "quota",
    "request failed",
    "timed out",
    "timeout",
)

_NEW_RELEASE_DAYS = 90
_RECENT_RELEASE_DAYS = 365
_MAX_STALENESS_DAYS = 90


def score_reflects_provider_answer(score: ExternalScore) -> bool:
    """True when the provider really answered (a score, or a definite "no match").

    Budget exhaustion, missing configuration and transport failures say nothing about
    the game, so they must not move `ratings_refreshed_at`.
    """
    if score.status != "unavailable":
        return True
    detail = (score.detail or "").lower()
    return not any(marker in detail for marker in _NOT_A_PROVIDER_ANSWER)


def refresh_counts(fresh_scores: Iterable[ExternalScore]) -> bool:
    return any(score_reflects_provider_answer(score) for score in fresh_scores)


def _recency_factor(game: Game, today: date) -> float:
    released = game.release_date
    if released is None or released.year <= 1970:
        return 1.0
    age_days = (today - released).days
    if age_days < 0:
        return 1.0  # announced, not out: nothing to rate yet
    if age_days <= _NEW_RELEASE_DAYS:
        return 3.0
    if age_days <= _RECENT_RELEASE_DAYS:
        return 2.0
    return 1.0


def _missing_primary_count(game: Game) -> int:
    live = {
        str(row.get("source"))
        for row in game.source_scores or []
        if isinstance(row, dict) and row.get("status") == "live" and score_value(row) is not None
    }
    return len(game.applicable_primary_sources - live)


def _staleness_factor(game: Game, now: datetime) -> float:
    refreshed = game.ratings_refreshed_at
    if refreshed is None:
        return 2.0
    if refreshed.tzinfo is None:
        refreshed = refreshed.replace(tzinfo=UTC)
    days = min(_MAX_STALENESS_DAYS, max(0, (now - refreshed).days))
    return 1.0 + days / 30


def rating_refresh_priority(game: Game, now: datetime | None = None) -> float:
    """Higher = refresh sooner."""
    now = now or datetime.now(UTC)
    reviews = sum(safe_review_count(row) for row in game.source_scores or [])
    popularity = max(
        math.log10(1 + reviews),
        float(game.rank_score or 0.0) / 25,
        float(game.metrix_score or 0.0) / 25,
    )
    return (
        (1 + popularity)
        * _recency_factor(game, now.date())
        * (1 + _missing_primary_count(game))
        * _staleness_factor(game, now)
    )


def top_refresh_candidates(
    games: Iterable[Game],
    *,
    limit: int | None,
    force: bool = False,
    release: Callable[[Game], None] | None = None,
) -> list[int]:
    """Ids of the games to refresh, best priority first.

    Streams the games and keeps only (priority, id) tuples; `release` is called on
    each game once it has been scored (callers pass `session.expunge`).
    """
    now = datetime.now(UTC)
    scored: list[tuple[float, int, int]] = []
    for game in games:
        if force or game_needs_rating_refresh(game, now):
            scored.append((rating_refresh_priority(game, now), -game.id, game.id))
        if release is not None:
            release(game)
    chosen = heapq.nlargest(limit, scored) if limit is not None else sorted(scored, reverse=True)
    return [game_id for _priority, _neg, game_id in chosen]
