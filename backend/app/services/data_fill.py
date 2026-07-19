"""Full catalog/data fill orchestration."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import desc, exists, func, select
from sqlalchemy.orm import noload

from ..config import get_settings
from ..database import SessionLocal
from ..heavy_jobs import HEAVY_JOB_LOCK
from ..integrations.cheapshark import import_cheapshark_deals
from ..integrations.free_to_game import import_free_to_game_games
from ..integrations.hltb import backfill_hltb_playtimes
from ..integrations.igdb_import import import_igdb_nintendo_games
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.rawg import import_catalog_to_size
from ..integrations.steamspy import import_steamspy_games
from ..integrations.sync import game_needs_rating_refresh, refresh_game_sources
from ..models import DataFillRun, ExternalId, Game, PriceSnapshot
from .metadata_backfill import metadata_backfill_batch
from .price_backfill import price_backfill_batch
from .primary_score_backfill import primary_score_backfill_batch, primary_score_coverage_status

log = logging.getLogger(__name__)

RATING_BUDGET_SOURCES = ("RAWG", "OpenCritic", "IGDB", "Steam", "SteamSpy")
METADATA_BUDGET_SOURCES = ("Steam", "RAWG", "IGDB")
PRICE_BUDGET_SOURCES = ("Steam", "ITAD", "CheapShark")


def _serialize_run(run: DataFillRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "force": run.force,
        "target_total": run.target_total,
        "result": run.result,
        "error": run.error,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _count_missing_external_ids() -> int:
    with SessionLocal() as db:
        has_external = exists(select(ExternalId.id).where(ExternalId.game_id == Game.id))
        return db.scalar(
            select(func.count(Game.id)).where(Game.content_type == "game", ~has_external)
        ) or 0


def data_fill_status() -> dict[str, object]:
    with SessionLocal() as db:
        total_games = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0
        missing_ratings = db.scalar(
            select(func.count(Game.id)).where(
                Game.content_type == "game",
                Game.ratings_refreshed_at.is_(None),
            )
        ) or 0
        missing_metadata = db.scalar(
            select(func.count(Game.id)).where(
                Game.content_type == "game",
                Game.metadata_refreshed_at.is_(None),
            )
        ) or 0
        missing_hltb = db.scalar(
            select(func.count(Game.id)).where(
                Game.content_type == "game",
                Game.hltb_id.is_(None),
                Game.playtime_minutes <= 0,
            )
        ) or 0
        has_price = exists(select(PriceSnapshot.id).where(PriceSnapshot.game_id == Game.id))
        missing_prices = db.scalar(
            select(func.count(Game.id)).where(Game.content_type == "game", ~has_price)
        ) or 0
        last_run = db.scalar(select(DataFillRun).order_by(desc(DataFillRun.started_at)).limit(1))
    primary_scores = primary_score_coverage_status()

    return {
        "running": HEAVY_JOB_LOCK.locked(),
        "catalog": {
            "total_games": total_games,
            "missing_ratings": missing_ratings,
            "missing_primary_scores": primary_scores["missing_score_slots"],
            "primary_complete_games": primary_scores["complete_games"],
            "missing_metadata": missing_metadata,
            "missing_hltb": missing_hltb,
            "missing_prices": missing_prices,
            "missing_external_ids": _count_missing_external_ids(),
        },
        "primary_scores": primary_scores,
        "rate_limits": get_rate_limiter().status(),
        "last_run": _serialize_run(last_run),
    }


def queue_data_fill_run(*, force: bool, target_total: int) -> dict[str, object]:
    with SessionLocal() as db:
        run = DataFillRun(
            status="queued",
            force=force,
            target_total=target_total,
            result={},
            started_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return _serialize_run(run) or {}


async def execute_data_fill_run(run_id: int, *, force: bool, target_total: int) -> None:
    if HEAVY_JOB_LOCK.locked():
        _finish_run(run_id, status="skipped", error="Another heavy job is already running.")
        return

    async with HEAVY_JOB_LOCK:
        _mark_run_running(run_id)
        result: dict[str, object] = {
            "catalog": {},
            "ratings": {},
            "primary_scores": {},
            "metadata": {},
            "hltb": {},
            "prices": {},
            "external_ids": {},
        }
        try:
            result["external_ids"] = {"before_missing": _count_missing_external_ids()}
            result["catalog"] = await _fill_catalog(target_total)
            result["primary_scores"] = await _fill_primary_scores(force=force)
            result["ratings"] = await _fill_ratings(force=force)
            result["metadata"] = await _fill_metadata()
            result["hltb"] = await _fill_hltb()
            result["prices"] = await _fill_prices()
            after_missing = _count_missing_external_ids()
            external_ids = dict(result["external_ids"])
            external_ids["after_missing"] = after_missing
            external_ids["matched"] = max(0, int(external_ids["before_missing"]) - after_missing)
            result["external_ids"] = external_ids
            _finish_run(run_id, status="complete", result=result)
        except Exception as exc:
            log.exception("Data fill run failed")
            _finish_run(run_id, status="failed", result=result, error=f"{type(exc).__name__}: {exc}")


def _mark_run_running(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(DataFillRun, run_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        db.commit()


def _finish_run(
    run_id: int,
    *,
    status: str,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    with SessionLocal() as db:
        run = db.get(DataFillRun, run_id)
        if run is None:
            return
        run.status = status
        if result is not None:
            run.result = result
        run.error = error
        run.finished_at = datetime.now(UTC)
        db.commit()


def _remaining_any(sources: tuple[str, ...]) -> bool:
    limiter = get_rate_limiter()
    return any(limiter.remaining(source) > 0 for source in sources)


async def _fill_catalog(target_total: int) -> dict[str, object]:
    cfg = get_settings()
    result: dict[str, object] = {}
    with SessionLocal() as db:
        current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0
        if current_total < target_total and get_rate_limiter().remaining("RAWG") > 0:
            result["RAWG"] = await import_catalog_to_size(db, target_total=target_total)
            current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or current_total

        if current_total < target_total and cfg.igdb_configured() and get_rate_limiter().remaining("IGDB") > 0:
            result["IGDB"] = await import_igdb_nintendo_games(db, target=min(5000, target_total - current_total))
            current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or current_total

        if current_total < target_total and get_rate_limiter().remaining("FreeToGame") > 0:
            result["FreeToGame"] = await import_free_to_game_games(db, target=min(1000, target_total - current_total))
            current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or current_total

        if current_total < target_total and get_rate_limiter().remaining("SteamSpy") > 0:
            result["SteamSpy"] = await import_steamspy_games(db, target=min(5000, target_total - current_total))
            current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or current_total

        if current_total < target_total and get_rate_limiter().remaining("CheapShark") > 0:
            result["CheapShark"] = await import_cheapshark_deals(db, target=min(2000, target_total - current_total))
            current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or current_total

        result["total_games"] = current_total
        result["target_total"] = target_total
    return result


async def _fill_ratings(*, force: bool) -> dict[str, int]:
    cfg = get_settings()
    refreshed = skipped = failed = 0
    with SessionLocal() as db:
        if force:
            game_ids = list(
                db.scalars(
                    select(Game.id)
                    .where(Game.content_type == "game")
                    .order_by(desc(Game.rank_score), desc(Game.metrix_score))
                ).all()
            )
        else:
            all_games = list(
                db.scalars(
                    select(Game)
                    .where(Game.content_type == "game")
                    .options(noload(Game.price_snapshots))
                    .order_by(desc(Game.rank_score), desc(Game.metrix_score))
                ).all()
            )
            now = datetime.now(UTC)
            game_ids = [game.id for game in all_games if game_needs_rating_refresh(game, now)]

    for game_id in game_ids:
        if refreshed >= cfg.DATA_FILL_RATING_BATCH_SIZE and not force:
            break
        if not _remaining_any(RATING_BUDGET_SOURCES):
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


async def _fill_primary_scores(*, force: bool) -> dict[str, object]:
    cfg = get_settings()
    if not _remaining_any(("Metacritic", "OpenCritic", "IGDB", "Steam")):
        return {
            "status": "budget_exhausted",
            "coverage": primary_score_coverage_status(),
        }
    result = await primary_score_backfill_batch(
        limit=cfg.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE,
        force=force,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def _fill_metadata() -> dict[str, object]:
    cfg = get_settings()
    if not _remaining_any(METADATA_BUDGET_SOURCES):
        return {"status": "budget_exhausted", "enriched": 0, "changed": 0}
    return await metadata_backfill_batch(
        limit=cfg.DATA_FILL_METADATA_BATCH_SIZE,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
        use_lock=False,
    )


async def _fill_hltb() -> dict[str, int]:
    cfg = get_settings()
    with SessionLocal() as db:
        return await backfill_hltb_playtimes(
            db,
            target=cfg.DATA_FILL_HLTB_TARGET,
            refresh_existing=False,
        )


async def _fill_prices() -> dict[str, int | str]:
    cfg = get_settings()
    if not _remaining_any(PRICE_BUDGET_SOURCES):
        return {"status": "budget_exhausted", "considered": 0, "stored": 0, "skipped": 0, "failed": 0}
    result = await price_backfill_batch(
        limit=cfg.DATA_FILL_PRICE_BATCH_SIZE,
        inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
    )
    return {"status": "ok", **result}


async def data_fill_loop() -> None:
    cfg = get_settings()
    if not cfg.DATA_FILL_ENABLED:
        return

    await asyncio.sleep(max(0, cfg.DATA_FILL_STARTUP_DELAY_SECONDS))
    while True:
        if not HEAVY_JOB_LOCK.locked():
            run = queue_data_fill_run(force=False, target_total=cfg.DATA_FILL_TARGET_TOTAL)
            run_id = int(run["id"])
            await execute_data_fill_run(run_id, force=False, target_total=cfg.DATA_FILL_TARGET_TOTAL)
        await asyncio.sleep(max(3600, int(cfg.DATA_FILL_INTERVAL_HOURS * 3600)))
