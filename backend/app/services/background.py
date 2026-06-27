"""
Background tasks: periodic rating refresh and metadata fixing.

Public API:
  rating_refresh_candidates(db)   -> list[Game]
  refresh_rating_batch(limit)     -> Awaitable[dict[str, int]]
  fix_year_batch(limit)           -> Awaitable[dict[str, int]]
  daily_refresh_loop()            -> Awaitable[None]  (runs forever; cancel to stop)
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import Game
from ..integrations.sync import game_needs_rating_refresh, refresh_game_sources
from ..integrations.steam import extract_steam_app_id, get_steam_release_dates
from .metadata import fix_game_year


log = logging.getLogger(__name__)


def rating_refresh_candidates(db: Session) -> list[Game]:
    games = list(db.scalars(select(Game).order_by(desc(Game.metrix_score))).all())
    now = datetime.now(UTC)
    stale = [g for g in games if game_needs_rating_refresh(g, now)]
    return sorted(stale, key=_refresh_priority_key)


def _refresh_priority_key(game: Game) -> tuple[int, float, float]:
    return (game.ratings_refreshed_at is not None, _refreshed_timestamp(game), -game.metrix_score)


def _refreshed_timestamp(game: Game) -> float:
    if game.ratings_refreshed_at is None:
        return 0.0
    ts = game.ratings_refreshed_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.timestamp()


async def refresh_rating_batch(limit: int) -> dict[str, int]:
    enriched = 0
    skipped = 0
    with SessionLocal() as db:
        for game in rating_refresh_candidates(db):
            if enriched >= limit:
                break
            if not game_needs_rating_refresh(game):
                skipped += 1
                continue
            await refresh_game_sources(db, game)
            enriched += 1
    return {"enriched": enriched, "skipped": skipped}


async def fix_year_batch(limit: int) -> dict[str, int]:
    fixed = 0
    skipped = 0
    with SessionLocal() as db:
        games = list(
            db.scalars(
                select(Game)
                .where(Game.release_year == 1970)
                .order_by(desc(Game.metrix_score))
                .limit(limit)
            ).all()
        )
        steam_fixed, _ = await _fix_steam_dates(db, games)
        fixed += steam_fixed

        fixed_ids = {g.id for g in games if g.release_year != 1970}
        for game in games:
            if game.id in fixed_ids:
                continue
            if await fix_game_year(game):
                db.add(game)
                fixed += 1
            else:
                skipped += 1

        db.commit()
    return {"fixed": fixed, "skipped": skipped}


async def _fix_steam_dates(db: Session, games: list[Game]) -> tuple[int, int]:
    games_by_app_id = {
        app_id: game
        for game in games
        if (app_id := extract_steam_app_id(game.slug, game.cover_url)) is not None
    }
    steam_dates = await get_steam_release_dates(list(games_by_app_id.keys()))
    fixed = 0
    for app_id, release_date in steam_dates.items():
        game = games_by_app_id[app_id]
        if release_date.year > 1970:
            game.release_date = release_date
            game.release_year = release_date.year
            db.add(game)
            fixed += 1
    return fixed, 0


async def daily_refresh_loop() -> None:
    cfg = get_settings()
    await asyncio.sleep(8)

    if cfg.STARTUP_RATING_REFRESH_LIMIT > 0:
        try:
            await refresh_rating_batch(cfg.STARTUP_RATING_REFRESH_LIMIT)
        except Exception:
            log.exception("Startup rating refresh failed")

    if cfg.STARTUP_METADATA_FIX_LIMIT > 0:
        try:
            await fix_year_batch(cfg.STARTUP_METADATA_FIX_LIMIT)
        except Exception:
            log.exception("Startup metadata fix failed")

    while True:
        await asyncio.sleep(cfg.RATING_REFRESH_INTERVAL_SECONDS)
        if cfg.DAILY_RATING_REFRESH_LIMIT > 0:
            try:
                await refresh_rating_batch(cfg.DAILY_RATING_REFRESH_LIMIT)
            except Exception:
                log.exception("Daily rating refresh failed")
        if cfg.DAILY_METADATA_FIX_LIMIT > 0:
            try:
                await fix_year_batch(cfg.DAILY_METADATA_FIX_LIMIT)
            except Exception:
                log.exception("Daily metadata fix failed")
