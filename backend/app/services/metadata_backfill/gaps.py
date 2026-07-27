"""Which games are missing which metadata, and how urgently.

Gap detection, gap-weighted urgency scoring, staleness rules, and candidate
selection — the "what to fix and when" half of the backfill.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from ...models import Game
from ..metadata import summary_needs_enrichment
from .sanitize import (
    GENERIC_GENRES,
    GENERIC_PLATFORMS,
    as_aware,
    is_missing_cover,
    system_requirements_need_repair,
    tupled,
)

DEFAULT_STALE_AFTER = timedelta(days=21)
DEFAULT_RETRY_AFTER = timedelta(hours=18)
COVER_RETRY_AFTER = timedelta(hours=6)

_GAP_WEIGHTS = {
    "cover": 100,
    "summary": 28,
    "developer": 16,
    "publisher": 16,
    "genres": 12,
    "platforms": 12,
    "screenshots": 10,
    "system_requirements": 8,
}
_DEFAULT_GAP_WEIGHT = 1
_CANDIDATE_POOL_MULTIPLIER = 10
_MIN_CANDIDATE_POOL = 200
_DEFAULT_CANDIDATE_LIMIT = 50


def field_gaps(game: Game) -> set[str]:
    gaps: set[str] = set()
    if is_missing_cover(game.cover_url):
        gaps.add("cover")
    if summary_needs_enrichment(game):
        gaps.add("summary")
    if not game.developer:
        gaps.add("developer")
    if not game.publisher:
        gaps.add("publisher")
    if tupled(game.genres) in GENERIC_GENRES:
        gaps.add("genres")
    if tupled(game.platforms) in GENERIC_PLATFORMS:
        gaps.add("platforms")
    if not game.screenshots:
        gaps.add("screenshots")
    if game.is_pc_applicable and system_requirements_need_repair(game.system_requirements):
        gaps.add("system_requirements")
    return gaps


def metadata_gap_score(game: Game) -> int:
    return sum(_GAP_WEIGHTS.get(gap, _DEFAULT_GAP_WEIGHT) for gap in field_gaps(game))


def game_needs_metadata_backfill(
    game: Game,
    now: datetime | None = None,
    *,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
    retry_after: timedelta = DEFAULT_RETRY_AFTER,
) -> bool:
    gaps = field_gaps(game)
    if not gaps:
        return False

    now = now or datetime.now(UTC)
    refreshed_at = as_aware(game.metadata_refreshed_at)
    if refreshed_at is None:
        return True

    effective_retry = COVER_RETRY_AFTER if "cover" in gaps else retry_after
    return now - refreshed_at >= min(stale_after, effective_retry)


def metadata_backfill_candidates(db: Session, limit: int | None = None) -> list[Game]:
    now = datetime.now(UTC)
    pool_limit = max((limit or _DEFAULT_CANDIDATE_LIMIT) * _CANDIDATE_POOL_MULTIPLIER, _MIN_CANDIDATE_POOL)
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .order_by(
                desc(Game.metadata_refreshed_at.is_(None)),
                asc(Game.metadata_refreshed_at),
                desc(Game.rank_score),
                desc(Game.metrix_score),
            )
            .limit(pool_limit)
        ).all()
    )
    due = [game for game in games if game_needs_metadata_backfill(game, now)]
    due.sort(key=lambda game: (-metadata_gap_score(game), _metadata_ts(game), -game.rank_score))
    return due[:limit] if limit is not None else due


def _metadata_ts(game: Game) -> float:
    refreshed_at = as_aware(game.metadata_refreshed_at)
    return refreshed_at.timestamp() if refreshed_at else 0.0
