"""Periodic data-identity maintenance: duplicate consolidation (daily)."""

import asyncio
import logging

from ..config import get_settings
from ..database import SessionLocal
from ..heavy_jobs import HEAVY_JOB_LOCK
from .deduplication import consolidate_duplicate_games
from .deduplication.store import duplicate_group_game_ids
from .job_heartbeat import record_job_run
from .seo import refresh_catalog_seo_states
from .steam_id_audit import audit_steam_ids

log = logging.getLogger(__name__)

_VERIFY_LIMIT = 300  # appdetails calls per run; paced by the audit's own delay
_STARTUP_DELAY_SECONDS = 240


async def run_duplicate_consolidation(*, dry_run: bool, verify_steam: bool = True) -> dict[str, object]:
    """Verify Steam ids of grouped games, then merge. `dry_run` writes nothing at all."""
    result: dict[str, object] = {}
    with SessionLocal() as db:
        group_ids = await asyncio.to_thread(duplicate_group_game_ids, db)
        db.expunge_all()  # one copy of the catalog in memory at a time (1 GB host)
        if verify_steam and group_ids:
            report = await audit_steam_ids(
                db, apply=not dry_run, limit=_VERIFY_LIMIT, game_ids=group_ids
            )
            result["steam_verification"] = {"checked": report.checked, "counts": report.counts}
        merged = await asyncio.to_thread(consolidate_duplicate_games, db, dry_run=dry_run)
        result.update(merged)
        if not dry_run and merged["removed"]:
            await asyncio.to_thread(_refresh_seo, db)
    return result


def _refresh_seo(db) -> None:
    refresh_catalog_seo_states(db)
    db.commit()


async def duplicate_consolidation_loop() -> None:
    """Runs forever, independent of STARTUP_CATALOG_MAINTENANCE_ENABLED."""
    cfg = get_settings()
    if not cfg.DUPLICATE_CONSOLIDATION_ENABLED:
        return
    await asyncio.sleep(_STARTUP_DELAY_SECONDS)
    interval_seconds = max(3600, int(cfg.DUPLICATE_CONSOLIDATION_INTERVAL_HOURS * 3600))
    while True:
        try:
            async with record_job_run("duplicate_consolidation", interval_seconds) as run:
                async with HEAVY_JOB_LOCK:
                    run.set(await run_duplicate_consolidation(dry_run=False))
        except Exception:
            log.exception("Duplicate consolidation failed")
        await asyncio.sleep(interval_seconds)
