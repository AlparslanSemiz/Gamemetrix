"""The individual fill stages. Each returns a summary dict for the run record.

Every stage checks provider budget headroom first and reports
`status: budget_exhausted` rather than burning the run on doomed calls.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, load_only, noload

from ...config import get_settings
from ...database import SessionLocal
from ...integrations.cheapshark import import_cheapshark_deals
from ...integrations.free_to_game import import_free_to_game_games
from ...integrations.hltb import backfill_hltb_playtimes
from ...integrations.igdb_import import (
    import_igdb_full_catalog,
)
from ...integrations.rate_limiter import get_rate_limiter
from ...integrations.rawg import import_catalog_to_size
from ...integrations.steamspy import import_steamspy_games
from ...integrations.steam_catalog import import_steam_official_catalog
from ...integrations.sync import game_needs_rating_refresh, refresh_game_sources
from ...models import Game
from ..catalog_quality import catalog_quality_batch, catalog_repair_batch
from ..endless import backfill_endless_batch
from ..igdb_optional_metadata_backfill import igdb_optional_metadata_backfill_batch
from ..igdb_playtime_backfill import igdb_playtime_backfill_batch
from ..igdb_score_backfill import igdb_score_backfill_batch
from ..metacritic_backfill import cheapshark_metacritic_backfill_batch
from ..metadata_backfill import metadata_backfill_batch
from ..price_backfill import price_backfill_batch
from ..primary_score_backfill import primary_score_backfill_batch, primary_score_coverage_status
from ..summarizer import refresh_summary_batch

log = logging.getLogger(__name__)

RATING_SCAN_CHUNK = 500
RATING_BUDGET_SOURCES = ("RAWG", "OpenCritic", "IGDB", "Steam")
METADATA_BUDGET_SOURCES = ("Steam", "IGDB", "Wikidata", "GameBrain", "RAWG")
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
_SECONDARY_CATALOG_IMPORTS: tuple[tuple[str, str, int, _SecondaryImporter], ...] = (
    ("Steam:catalog", "Steam", 500, lambda db, target: import_steam_official_catalog(db, target=target)),
    ("IGDB:full", "IGDB", 5000, lambda db, target: import_igdb_full_catalog(db, target=target)),
    ("FreeToGame", "FreeToGame", 1000, lambda db, target: import_free_to_game_games(db, target=target)),
    ("SteamSpy", "SteamSpy", 5000, lambda db, target: import_steamspy_games(db, target=target)),
    ("CheapShark", "CheapShark", 2000, lambda db, target: import_cheapshark_deals(db, target=target)),
)


def catalog_import_target(
    *,
    source: str,
    cap: int,
    current_total: int,
    target_total: int,
) -> int:
    return max(0, min(cap, target_total - current_total))


async def fill_catalog(target_total: int) -> dict[str, object]:
    cfg = get_settings()
    result: dict[str, object] = {}
    with SessionLocal() as db:
        current_total = _game_count(db)
        for result_key, source, cap, importer in _SECONDARY_CATALOG_IMPORTS:
            if source == "IGDB" and not cfg.igdb_configured():
                continue
            if source == "Steam" and not cfg.steam_configured():
                continue
            if get_rate_limiter().remaining(source) <= 0:
                continue
            import_target = catalog_import_target(
                source=source,
                cap=cap,
                current_total=current_total,
                target_total=target_total,
            )
            if import_target <= 0:
                continue
            try:
                result[result_key] = await importer(db, import_target)
            except Exception as exc:
                db.rollback()
                log.warning("%s catalog import failed (%s)", result_key, type(exc).__name__)
                result[result_key] = {
                    "status": "failed",
                    "error": type(exc).__name__,
                }
                continue
            current_total = _game_count(db) or current_total

        # RAWG is the scarce free quota and also feeds Metacritic. Use it only
        # after the generous/free catalog sources have made all possible progress.
        if (
            current_total < target_total
            and cfg.rawg_configured()
            and get_rate_limiter().remaining("RAWG") > 0
        ):
            try:
                result["RAWG"] = await import_catalog_to_size(db, target_total=target_total)
                current_total = _game_count(db) or current_total
            except Exception as exc:
                db.rollback()
                log.warning("RAWG catalog import failed (%s)", type(exc).__name__)
                result["RAWG"] = {
                    "status": "failed",
                    "error": type(exc).__name__,
                }

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
            .options(
                load_only(
                    Game.id,
                    Game.platforms,
                    Game.source_scores,
                    Game.ratings_refreshed_at,
                    Game.data_complete,
                ),
                noload(Game.price_snapshots),
            )
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


async def fill_metacritic() -> dict[str, object]:
    """Seed Metacritic from CheapShark (free) before scoring, sparing RAWG budget."""
    cfg = get_settings()
    if not remaining_any(("CheapShark",)):
        return {"status": "budget_exhausted", "seeded": 0}
    result = await cheapshark_metacritic_backfill_batch(
        limit=cfg.DATA_FILL_METADATA_BATCH_SIZE,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


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


async def fill_igdb_playtime() -> dict[str, object]:
    """Fill playtime HLTB missed, from IGDB's official time-to-beat endpoint."""
    cfg = get_settings()
    if not cfg.igdb_configured() or not remaining_any(("IGDB",)):
        return {"status": "skipped", "filled": 0}
    result = await igdb_playtime_backfill_batch(
        limit=cfg.DATA_FILL_HLTB_TARGET,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def fill_igdb_scores(*, force: bool) -> dict[str, object]:
    """Fill known top-10k IGDB ratings with up to 500 games per API call."""
    cfg = get_settings()
    if not cfg.igdb_configured() or not remaining_any(("IGDB",)):
        return {"status": "skipped", "filled": 0}
    result = await igdb_score_backfill_batch(
        limit=cfg.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE,
        force=force,
        inter_batch_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def fill_igdb_optional_metadata() -> dict[str, object]:
    """Batch-fill official websites and game modes without making them blockers."""
    cfg = get_settings()
    if not cfg.igdb_configured() or not remaining_any(("IGDB",)):
        return {"status": "skipped", "website_filled": 0, "modes_filled": 0}
    result = await igdb_optional_metadata_backfill_batch(
        limit=cfg.DATA_FILL_HLTB_TARGET,
        inter_batch_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def fill_endless() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await backfill_endless_batch(db, cfg.ENDLESS_BACKFILL_BATCH_SIZE)


async def fill_summaries() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await refresh_summary_batch(
            db,
            cfg.SUMMARY_SHORTEN_BATCH_SIZE,
            cfg.SUMMARY_QUALITY_AI_LIMIT,
        )


async def audit_catalog_quality() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await catalog_quality_batch(db, cfg.CATALOG_QUALITY_BATCH_SIZE)


async def repair_catalog_quality() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await catalog_repair_batch(db, cfg.CATALOG_REPAIR_BATCH_SIZE)
