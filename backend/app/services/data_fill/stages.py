"""The individual fill stages. Each returns a summary dict for the run record.

Every stage checks provider budget headroom first and reports
`status: budget_exhausted` rather than burning the run on doomed calls.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, noload

from ...config import get_settings
from ...database import SessionLocal
from ...integrations.cheapshark import import_cheapshark_deals
from ...integrations.free_to_game import import_free_to_game_games
from ...integrations.hltb import backfill_hltb_playtimes
from ...integrations.igdb_import import import_igdb_nintendo_games
from ...integrations.rate_limiter import get_rate_limiter
from ...integrations.rawg import import_catalog_to_size
from ...integrations.steamspy import import_steamspy_games
from ...integrations.sync import game_needs_rating_refresh, refresh_game_sources
from ...models import Game
from ..endless import backfill_endless_batch
from ..metadata_backfill import metadata_backfill_batch
from ..nongame_cleanup import nongame_cleanup_batch
from ..price_backfill import price_backfill_batch
from ..primary_score_backfill import primary_score_backfill_batch, primary_score_coverage_status
from ..summarizer import shorten_summary_batch

log = logging.getLogger(__name__)

RATING_SCAN_CHUNK = 500
RATING_BUDGET_SOURCES = ("RAWG", "OpenCritic", "IGDB", "Steam", "SteamSpy")
METADATA_BUDGET_SOURCES = ("Steam", "RAWG", "IGDB")
PRICE_BUDGET_SOURCES = ("Steam", "ITAD", "CheapShark")
PRIMARY_SCORE_BUDGET_SOURCES = ("Metacritic", "OpenCritic", "IGDB", "Steam")

MAX_BATCH_CYCLES = 100

_SecondaryImporter = Callable[[Session, int], Awaitable[dict]]


def remaining_any(sources: tuple[str, ...]) -> bool:
    limiter = get_rate_limiter()
    return any(limiter.remaining(source) > 0 for source in sources)


def _game_count(db: Session) -> int:
    return db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0


# source -> (per-run import cap, importer). RAWG is handled separately because it
# takes an absolute catalog target rather than a remaining-headroom count.
_SECONDARY_CATALOG_IMPORTS: tuple[tuple[str, int, _SecondaryImporter], ...] = (
    ("IGDB", 5000, lambda db, target: import_igdb_nintendo_games(db, target=target)),
    ("FreeToGame", 1000, lambda db, target: import_free_to_game_games(db, target=target)),
    ("SteamSpy", 5000, lambda db, target: import_steamspy_games(db, target=target)),
    ("CheapShark", 2000, lambda db, target: import_cheapshark_deals(db, target=target)),
)


async def fill_catalog(target_total: int) -> dict[str, object]:
    cfg = get_settings()
    result: dict[str, object] = {}
    with SessionLocal() as db:
        current_total = _game_count(db)
        if current_total < target_total and get_rate_limiter().remaining("RAWG") > 0:
            result["RAWG"] = await import_catalog_to_size(db, target_total=target_total)
            current_total = _game_count(db) or current_total

        for source, cap, importer in _SECONDARY_CATALOG_IMPORTS:
            if current_total >= target_total:
                break
            if source == "IGDB" and not cfg.igdb_configured():
                continue
            if get_rate_limiter().remaining(source) <= 0:
                continue
            result[source] = await importer(db, min(cap, target_total - current_total))
            current_total = _game_count(db) or current_total

        result["total_games"] = current_total
        result["target_total"] = target_total
    return result


def _rating_refresh_candidates(force: bool) -> list[int]:
    with SessionLocal() as db:
        if force:
            return list(db.scalars(
                select(Game.id)
                .where(Game.content_type == "game")
                .order_by(desc(Game.rank_score), desc(Game.metrix_score))
            ).all())

        # Only the ids survive this scan, so the rows are streamed and detached as
        # they are checked. Materialising the whole catalog here held every Game
        # object in the identity map at once and helped OOM the backend container.
        now = datetime.now(UTC)
        game_ids: list[int] = []
        for game in db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .options(noload(Game.price_snapshots))
            .order_by(desc(Game.rank_score), desc(Game.metrix_score))
            .execution_options(yield_per=RATING_SCAN_CHUNK)
        ):
            if game_needs_rating_refresh(game, now):
                game_ids.append(game.id)
            db.expunge(game)
        return game_ids


async def fill_ratings(*, force: bool) -> dict[str, int]:
    cfg = get_settings()
    refreshed = skipped = failed = 0
    for game_id in _rating_refresh_candidates(force):
        if not remaining_any(RATING_BUDGET_SOURCES):
            break
        if cfg.DATA_FILL_INTER_GAME_DELAY > 0:
            await asyncio.sleep(cfg.DATA_FILL_INTER_GAME_DELAY)
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None:
                skipped += 1
                continue
            try:
                await refresh_game_sources(db, game)
                refreshed += 1
            except Exception:
                failed += 1
    return {"refreshed": refreshed, "skipped": skipped, "failed": failed}


async def fill_primary_scores(*, force: bool) -> dict[str, object]:
    cfg = get_settings()
    if not remaining_any(PRIMARY_SCORE_BUDGET_SOURCES):
        return {"status": "budget_exhausted", "coverage": primary_score_coverage_status()}
    result = await primary_score_backfill_batch(
        limit=cfg.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE,
        force=force,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def _accumulate_batches(
    budget_sources: tuple[str, ...],
    counter_keys: tuple[str, ...],
    run_batch: Callable[[], Awaitable[dict]],
    should_stop: Callable[[dict], bool],
) -> dict[str, object]:
    """Repeat a batch until budget runs out, it stops making progress, or the cycle cap."""
    totals: dict[str, object] = {"status": "ok", "cycles": 0}
    for key in counter_keys:
        totals[key] = 0

    while remaining_any(budget_sources) and int(totals["cycles"]) < MAX_BATCH_CYCLES:
        batch = await run_batch()
        totals["cycles"] = int(totals["cycles"]) + 1
        for key in counter_keys:
            totals[key] = int(totals[key]) + int(batch.get(key, 0))
        if should_stop(batch):
            break

    if not remaining_any(budget_sources):
        totals["status"] = "budget_exhausted"
    return totals


async def fill_metadata() -> dict[str, object]:
    cfg = get_settings()
    if not remaining_any(METADATA_BUDGET_SOURCES):
        return {"status": "budget_exhausted", "enriched": 0, "changed": 0}

    return await _accumulate_batches(
        METADATA_BUDGET_SOURCES,
        ("considered", "enriched", "changed", "skipped", "failed"),
        lambda: metadata_backfill_batch(
            limit=cfg.DATA_FILL_METADATA_BATCH_SIZE,
            inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
            use_lock=False,
            refresh_seo=False,
        ),
        lambda batch: int(batch.get("considered", 0)) == 0
        or (int(batch.get("enriched", 0)) == 0 and int(batch.get("changed", 0)) == 0),
    )


async def fill_prices() -> dict[str, object]:
    cfg = get_settings()
    if not remaining_any(PRICE_BUDGET_SOURCES):
        return {"status": "budget_exhausted", "considered": 0, "stored": 0, "skipped": 0, "failed": 0}

    return await _accumulate_batches(
        PRICE_BUDGET_SOURCES,
        ("considered", "stored", "skipped", "failed"),
        lambda: price_backfill_batch(
            limit=cfg.DATA_FILL_PRICE_BATCH_SIZE,
            inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
            refresh_seo=False,
        ),
        lambda batch: int(batch.get("considered", 0)) == 0,
    )


async def fill_hltb() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await backfill_hltb_playtimes(
            db, target=cfg.DATA_FILL_HLTB_TARGET, refresh_existing=False
        )


async def fill_endless() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await backfill_endless_batch(db, cfg.ENDLESS_BACKFILL_BATCH_SIZE)


async def fill_summaries() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await shorten_summary_batch(db, cfg.SUMMARY_SHORTEN_BATCH_SIZE)


async def clean_nongames() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await nongame_cleanup_batch(db, cfg.NONGAME_CLEANUP_BATCH_SIZE)
