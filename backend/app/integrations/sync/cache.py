"""Reading still-fresh scores back out of a game's stored rows."""

from datetime import UTC, datetime, timedelta

from ...models import Game
from ..types import ExternalScore
from .constants import CACHE_TTL, DATA_COMPLETE_TTL
from .values import review_count, score_value

_MAX_DETAIL_LENGTH = 1000
_DEFAULT_SCALE = 100


def cached_score(
    source_scores: list[dict[str, object]],
    source_name: str,
    ttl: timedelta | None = None,
    *,
    live_only: bool = False,
) -> ExternalScore | None:
    effective_ttl = ttl if ttl is not None else CACHE_TTL
    for row in source_scores:
        if row.get("source") != source_name:
            continue
        score = _usable_cached_value(row, live_only=live_only)
        if score is None:
            continue
        if not _is_fresh(row, effective_ttl):
            continue
        entry = _to_external_score(row, source_name, score)
        if entry is not None:
            return entry
    return None


def _usable_cached_value(row: dict[str, object], *, live_only: bool) -> float | None:
    status = str(row.get("status", "live"))
    score = score_value(row)
    if status == "unavailable" and not live_only:
        score = 0.0
    if score is None or (live_only and status != "live"):
        return None
    return score


def _is_fresh(row: dict[str, object], ttl: timedelta) -> bool:
    refreshed_at = row.get("refreshed_at")
    if not isinstance(refreshed_at, str):
        return False
    try:
        refreshed_time = datetime.fromisoformat(refreshed_at)
    except ValueError:
        return False
    return datetime.now(UTC) - refreshed_time <= ttl


def _to_external_score(
    row: dict[str, object],
    source_name: str,
    score: float,
) -> ExternalScore | None:
    try:
        return ExternalScore(
            source=source_name,
            score=score,
            scale=int(row.get("scale", _DEFAULT_SCALE)),
            status=str(row.get("status", "live")),  # type: ignore[arg-type]
            detail=str(row.get("detail", "Cached score"))[:_MAX_DETAIL_LENGTH],
            review_count=review_count(row),
        )
    except (TypeError, ValueError, OverflowError):
        return None


def game_needs_rating_refresh(game: Game, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if game.ratings_refreshed_at is None:
        return True

    refreshed_at = game.ratings_refreshed_at
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=UTC)
    ttl = DATA_COMPLETE_TTL if game.data_complete else CACHE_TTL
    if now - refreshed_at >= ttl:
        return True

    live = {
        str(s.get("source"))
        for s in game.source_scores
        if s.get("status") == "live" and score_value(s) is not None
    }
    return any(src not in live for src in game.applicable_primary_sources)
