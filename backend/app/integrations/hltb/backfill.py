"""Applying HLTB matches to games, and the rate-limited catalog sweep."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy.orm import Session

from ...models import Game
from ..rate_limiter import get_rate_limiter
from .client import HltbClient
from .matching import HltbMatch, best_playtime_minutes

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(days=30)
_MAX_COVER_URL_LENGTH = 500
_MISSING_COVER_VALUES = {"", "none", "null"}

_HLTB_MINUTE_FIELDS = {
    "hltb_main_story_minutes": "main_story_minutes",
    "hltb_main_extra_minutes": "main_extra_minutes",
    "hltb_completionist_minutes": "completionist_minutes",
    "hltb_all_styles_minutes": "all_styles_minutes",
}


def _is_missing_cover(value: str | None) -> bool:
    return not value or value.strip().lower() in _MISSING_COVER_VALUES


def _igdb_cover_from_source_scores(game: Game) -> str | None:
    for score in game.source_scores or []:
        raw_response = score.get("response")
        if not isinstance(raw_response, dict):
            continue
        cover = raw_response.get("cover")
        if not isinstance(cover, dict):
            continue
        url = cover.get("url")
        if not isinstance(url, str) or not url:
            continue
        return url.replace("//", "https://", 1).replace("t_thumb", "t_cover_big_2x")
    return None


def repair_missing_cover(game: Game, hltb_image_url: str | None = None) -> bool:
    if not _is_missing_cover(game.cover_url):
        return False
    cover_url = hltb_image_url or _igdb_cover_from_source_scores(game)
    if not cover_url:
        return False
    game.cover_url = cover_url[:_MAX_COVER_URL_LENGTH]
    game.image_url = cover_url[:_MAX_COVER_URL_LENGTH]
    return True


def apply_hltb_match(game: Game, match: HltbMatch, refresh_existing: bool = False) -> bool:
    now = datetime.now(UTC)
    changed = _apply_identity(game, match)
    changed = _apply_minutes(game, match) or changed
    changed = _apply_primary_playtime(game, match, refresh_existing) or changed
    changed = repair_missing_cover(game, match.image_url) or changed

    if game.hltb_refreshed_at != now:
        game.hltb_refreshed_at = now
        changed = True
    return changed


def _apply_identity(game: Game, match: HltbMatch) -> bool:
    changed = False
    for field, value in (("hltb_id", match.hltb_id), ("hltb_url", match.url)):
        if getattr(game, field) != value:
            setattr(game, field, value)
            changed = True
    return changed


def _apply_minutes(game: Game, match: HltbMatch) -> bool:
    changed = False
    for game_field, match_field in _HLTB_MINUTE_FIELDS.items():
        value = getattr(match, match_field)
        if getattr(game, game_field) != value:
            setattr(game, game_field, value)
            changed = True
    return changed


def _apply_primary_playtime(game: Game, match: HltbMatch, refresh_existing: bool) -> bool:
    minutes = best_playtime_minutes(match)
    if minutes > 0 and (refresh_existing or (game.playtime_minutes or 0) <= 0):
        game.playtime_minutes = minutes
        return True
    return False


def _cover_missing_clause():
    return or_(
        Game.cover_url.is_(None),
        func.trim(Game.cover_url) == "",
        func.lower(Game.cover_url).in_(("none", "null")),
    )


def _backfill_query(target: int, refresh_existing: bool) -> Select[tuple[Game]]:
    cover_missing = _cover_missing_clause()
    query = select(Game).where(Game.content_type == "game")
    if refresh_existing:
        query = query.where(
            or_(Game.hltb_id.is_not(None), Game.playtime_minutes > 0, cover_missing)
        )
    else:
        query = query.where(
            or_(Game.hltb_id.is_(None), Game.playtime_minutes <= 0, cover_missing),
            or_(
                Game.hltb_refreshed_at.is_(None),
                Game.hltb_refreshed_at < datetime.now(UTC) - STALE_AFTER,
            ),
        )
    return query.order_by(desc(Game.rank_score), desc(Game.metrix_score)).limit(target)


async def backfill_hltb_playtimes(
    db: Session,
    target: int = 200,
    refresh_existing: bool = False,
    delay_seconds: float | None = None,
) -> dict[str, int]:
    if delay_seconds is None:
        from ...config import get_settings
        delay_seconds = get_settings().HLTB_REQUEST_DELAY_SECONDS

    games = list(db.scalars(_backfill_query(target, refresh_existing)).all())
    client = HltbClient()
    imported = skipped = repaired_covers = 0

    for game in games:
        if repair_missing_cover(game):
            repaired_covers += 1
            imported += 1

        if not await get_rate_limiter().acquire("HLTB"):
            _commit_if_dirty(db, game)
            break
        try:
            match = await client.search(game.title, release_year=game.release_year)
        except Exception as exc:
            log.warning("HLTB backfill paused after %s", type(exc).__name__)
            _commit_if_dirty(db, game)
            break

        if match and apply_hltb_match(game, match, refresh_existing=refresh_existing):
            imported += 1
        else:
            skipped += 1

        game.hltb_refreshed_at = datetime.now(UTC)
        db.add(game)
        db.commit()
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return {"imported": imported, "skipped": skipped, "repaired_covers": repaired_covers}


def _commit_if_dirty(db: Session, game: Game) -> None:
    if game in db.dirty:
        db.commit()
