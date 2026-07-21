"""
Background tasks: periodic rating refresh and metadata fixing.

Public API:
  rating_refresh_candidates(db)                -> list[Game]
  refresh_rating_batch(limit)                  -> Awaitable[dict[str, int]]
  refresh_all_games(concurrency, force)        -> Awaitable[dict[str, int]]
  fix_year_batch(limit)                        -> Awaitable[dict[str, int]]
  daily_refresh_loop()                         -> Awaitable[None]  (runs forever; cancel to stop)
  metadata_backfill_loop()                     -> Awaitable[None]  (runs forever; cancel to stop)
  hltb_backfill_loop()                         -> Awaitable[None]  (runs forever; cancel to stop)
  summary_backfill_loop()                      -> Awaitable[None]  (runs forever; cancel to stop)
  purge_expired_raw_analytics(db)              -> int
  raw_analytics_retention_loop()               -> Awaitable[None]  (runs forever; cancel to stop)
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import asc, desc, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..heavy_jobs import HEAVY_JOB_LOCK
from ..models import Game, VisitEvent
from ..integrations.hltb import backfill_hltb_playtimes
from ..integrations.sync import game_needs_rating_refresh, refresh_game_sources
from ..integrations.steam import extract_steam_app_id, get_steam_release_dates
from .metadata import fix_game_year
from .metadata_backfill import metadata_backfill_batch
from .summarizer import shorten_summary_batch


log = logging.getLogger(__name__)

_RETENTION_STARTUP_DELAY_SECONDS = 120
_RETENTION_INTERVAL_SECONDS = 6 * 60 * 60


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


# Shared with app/routers/imports.py — see app/heavy_jobs.py. Ensures an
# import and a refresh-all can never run concurrently on this 1GB host.
_REFRESH_ALL_LOCK = HEAVY_JOB_LOCK


async def refresh_all_games(
    concurrency: int = 3,
    force: bool = False,
    inter_game_delay: float = 0.3,
) -> dict[str, int]:
    """
    Refresh every game in the DB concurrently (semaphore-bounded).

    Only one run at a time (guarded by _REFRESH_ALL_LOCK).
    Non-force: skips games that game_needs_rating_refresh() considers fresh.
    Force: refreshes all regardless of cache state.
    inter_game_delay: seconds to sleep after acquiring the semaphore slot,
                      spreading requests over time to respect API rate limits.
    """
    if _REFRESH_ALL_LOCK.locked():
        return {"enriched": 0, "skipped": 0, "status": "already_running"}  # type: ignore[return-value]

    async with _REFRESH_ALL_LOCK:
        with SessionLocal() as db:
            all_games = list(
                db.scalars(
                    select(Game)
                    .where(Game.content_type == "game")
                    .order_by(asc(Game.ratings_refreshed_at))
                ).all()
            )

        sem = asyncio.Semaphore(concurrency)
        enriched = 0
        skipped = 0
        now = datetime.now(UTC)

        async def _refresh_one(game_id: int) -> bool:
            async with sem:
                if inter_game_delay > 0:
                    await asyncio.sleep(inter_game_delay)
                with SessionLocal() as db:
                    game = db.get(Game, game_id)
                    if game is None:
                        return False
                    if not force and not game_needs_rating_refresh(game, now):
                        return False
                    try:
                        await refresh_game_sources(db, game, force=force)
                        return True
                    except Exception:
                        log.debug("refresh_all_games: failed for game_id=%d", game_id, exc_info=True)
                        return False

        results = await asyncio.gather(*[_refresh_one(g.id) for g in all_games])
        for did_refresh in results:
            if did_refresh:
                enriched += 1
            else:
                skipped += 1

        if enriched:
            with SessionLocal() as db:
                from .seo import refresh_catalog_seo_states
                refresh_catalog_seo_states(db)
                db.commit()

        log.info("refresh_all_games done: %d refreshed, %d skipped", enriched, skipped)
        return {"enriched": enriched, "skipped": skipped}


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
        if enriched:
            from .seo import refresh_catalog_seo_states
            refresh_catalog_seo_states(db)
            db.commit()
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
    """
    Runs forever. On startup, then every REFRESH_ALL_INTERVAL_HOURS:
      1. refresh_all_games — fetches missing/stale scores for all games,
         respecting per-source daily budgets and inter-game delay.
      2. fix_year_batch   — corrects games still showing release_year=1970.

    The rate limiter resets at midnight, so the next cycle after midnight
    will pick up sources that were budget-exhausted in earlier cycles.
    """
    cfg = get_settings()
    await asyncio.sleep(30)

    concurrency = cfg.REFRESH_ALL_CONCURRENCY
    delay = cfg.REFRESH_ALL_INTER_GAME_DELAY

    # Startup pass
    try:
        await refresh_all_games(concurrency=concurrency, force=False, inter_game_delay=delay)
    except Exception:
        log.exception("Startup full refresh failed")

    if cfg.STARTUP_METADATA_FIX_LIMIT > 0:
        try:
            await fix_year_batch(cfg.STARTUP_METADATA_FIX_LIMIT)
        except Exception:
            log.exception("Startup metadata fix failed")

    interval_seconds = int(cfg.REFRESH_ALL_INTERVAL_HOURS * 3600)
    while True:
        await asyncio.sleep(interval_seconds)
        log.info("Periodic refresh starting (every %.1fh)", cfg.REFRESH_ALL_INTERVAL_HOURS)
        try:
            await refresh_all_games(concurrency=concurrency, force=False, inter_game_delay=delay)
        except Exception:
            log.exception("Periodic full refresh failed")
        if cfg.DAILY_METADATA_FIX_LIMIT > 0:
            try:
                await fix_year_batch(cfg.DAILY_METADATA_FIX_LIMIT)
            except Exception:
                log.exception("Periodic metadata fix failed")


async def metadata_backfill_loop() -> None:
    """
    Runs forever in small batches. This backfills non-score metadata such as
    covers, summaries, screenshots, requirements, websites, and external IDs.

    The job is intentionally separate from refresh_all_games: it spreads API
    calls across the day and uses the shared heavy-job lock plus per-source
    budgets, so imports / full score refreshes / metadata backfill do not stack.
    """
    cfg = get_settings()
    await asyncio.sleep(45)

    limit = cfg.METADATA_BACKFILL_BATCH_SIZE
    delay = cfg.METADATA_BACKFILL_INTER_GAME_DELAY

    if cfg.STARTUP_METADATA_BACKFILL_LIMIT > 0:
        try:
            await metadata_backfill_batch(
                limit=cfg.STARTUP_METADATA_BACKFILL_LIMIT,
                inter_game_delay=delay,
            )
        except Exception:
            log.exception("Startup metadata backfill failed")

    interval_seconds = max(60, int(cfg.METADATA_BACKFILL_INTERVAL_MINUTES * 60))
    while True:
        await asyncio.sleep(interval_seconds)
        log.info("Periodic metadata backfill starting (every %.1fm)", cfg.METADATA_BACKFILL_INTERVAL_MINUTES)
        try:
            await metadata_backfill_batch(limit=limit, inter_game_delay=delay)
        except Exception:
            log.exception("Periodic metadata backfill failed")


def purge_expired_raw_analytics(db: Session) -> int:
    """Redact raw IP/user-agent past the retention window. Hashes are kept."""
    cfg = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=cfg.ANALYTICS_RAW_IP_RETENTION_DAYS)
    result = db.execute(
        update(VisitEvent)
        .where(VisitEvent.created_at < cutoff, VisitEvent.ip_address.is_not(None))
        .values(ip_address=None, user_agent=None)
    )
    db.commit()
    return int(result.rowcount or 0)


async def raw_analytics_retention_loop() -> None:
    """
    Enforces the raw-IP retention window on a schedule.

    Runs unconditionally — including when raw-IP storage is switched off, which
    is exactly when previously stored addresses still need purging.
    """
    await asyncio.sleep(_RETENTION_STARTUP_DELAY_SECONDS)
    while True:
        try:
            with SessionLocal() as db:
                redacted = purge_expired_raw_analytics(db)
            if redacted:
                log.info("Redacted raw network data on %d visit events", redacted)
        except Exception:
            log.exception("Raw analytics retention sweep failed")
        await asyncio.sleep(_RETENTION_INTERVAL_SECONDS)


async def hltb_backfill_loop() -> None:
    """
    Fills HowLongToBeat playtimes in small periodic batches.

    Playtime is the one catalog field no rating source provides, so without this
    loop the playtime filter has almost nothing to match against. HLTB is scraped
    rather than an official API, hence the deliberately unhurried pacing.
    """
    cfg = get_settings()
    await asyncio.sleep(90)

    interval_seconds = max(60, int(cfg.HLTB_BACKFILL_INTERVAL_MINUTES * 60))
    while True:
        try:
            with SessionLocal() as db:
                result = await backfill_hltb_playtimes(
                    db,
                    target=cfg.HLTB_BACKFILL_BATCH_SIZE,
                    delay_seconds=cfg.HLTB_BACKFILL_INTER_GAME_DELAY,
                )
            log.info(
                "HLTB backfill: %s imported, %s skipped, %s covers repaired",
                result["imported"],
                result["skipped"],
                result["repaired_covers"],
            )
        except Exception:
            log.exception("Periodic HLTB backfill failed")
        await asyncio.sleep(interval_seconds)


async def summary_backfill_loop() -> None:
    """
    Shortens long game descriptions into a compact `summary_short` in small
    periodic batches, so the catalog list shows a complete short blurb instead
    of a mid-sentence, ellipsis-clamped full summary.

    Uses Groq when GROQ_API_KEY is configured, otherwise falls back to a
    clean sentence-boundary extract (see services/summarizer.py). Runs on its
    own schedule, independent of the score/metadata refresh loops.
    """
    cfg = get_settings()
    await asyncio.sleep(120)

    if cfg.SUMMARY_SHORTEN_STARTUP_LIMIT > 0:
        try:
            with SessionLocal() as db:
                await shorten_summary_batch(db, cfg.SUMMARY_SHORTEN_STARTUP_LIMIT)
        except Exception:
            log.exception("Startup summary backfill failed")

    interval_seconds = max(60, int(cfg.SUMMARY_SHORTEN_INTERVAL_MINUTES * 60))
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            with SessionLocal() as db:
                result = await shorten_summary_batch(db, cfg.SUMMARY_SHORTEN_BATCH_SIZE)
            log.info(
                "Summary backfill: %s shortened, %s skipped",
                result["shortened"],
                result["skipped"],
            )
        except Exception:
            log.exception("Periodic summary backfill failed")
