"""Rate-limited batch loop over backfill candidates, one game per DB session."""

from __future__ import annotations

import asyncio
import logging

from ...database import SessionLocal
from ...heavy_jobs import HEAVY_JOB_LOCK
from ...models import Game
from ..seo import refresh_catalog_seo_states
from .gaps import game_needs_metadata_backfill, metadata_backfill_candidates
from .sources import refresh_game_metadata

log = logging.getLogger(__name__)

METADATA_BACKFILL_LOCK = HEAVY_JOB_LOCK

_DEFAULT_LIMIT = 24
_DEFAULT_INTER_GAME_DELAY = 0.5

_ALREADY_RUNNING = {
    "status": "already_running",
    "considered": 0,
    "enriched": 0,
    "changed": 0,
    "skipped": 0,
    "budget_skipped": {},
    "failed": 0,
}


async def metadata_backfill_batch(
    limit: int = _DEFAULT_LIMIT,
    *,
    inter_game_delay: float = _DEFAULT_INTER_GAME_DELAY,
    use_lock: bool = True,
    refresh_seo: bool = True,
) -> dict[str, object]:
    if not use_lock:
        return await _run_batch(limit=limit, inter_game_delay=inter_game_delay, refresh_seo=refresh_seo)
    if METADATA_BACKFILL_LOCK.locked():
        return dict(_ALREADY_RUNNING)
    async with METADATA_BACKFILL_LOCK:
        return await _run_batch(limit=limit, inter_game_delay=inter_game_delay, refresh_seo=refresh_seo)


class _BatchTally:
    def __init__(self) -> None:
        self.enriched = 0
        self.changed = 0
        self.skipped = 0
        self.failed = 0
        self.budget_skipped: dict[str, int] = {}

    def record(self, result: dict[str, object]) -> None:
        if not result["attempted"]:
            self.skipped += 1
        else:
            self.enriched += 1
        if result["changed"]:
            self.changed += 1
        for source in result["budget_skipped"]:
            self.budget_skipped[source] = self.budget_skipped.get(source, 0) + 1


async def _run_batch(*, limit: int, inter_game_delay: float, refresh_seo: bool) -> dict[str, object]:
    with SessionLocal() as db:
        candidate_ids = [game.id for game in metadata_backfill_candidates(db, limit=limit)]

    tally = _BatchTally()
    for game_id in candidate_ids:
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        await _process_candidate(game_id, tally)

    if tally.changed and refresh_seo:
        with SessionLocal() as db:
            refresh_catalog_seo_states(db)
            db.commit()

    log.info(
        "metadata_backfill_batch done: %d enriched, %d changed, %d skipped, %d failed",
        tally.enriched, tally.changed, tally.skipped, tally.failed,
    )
    return {
        "status": "ok",
        "considered": len(candidate_ids),
        "enriched": tally.enriched,
        "changed": tally.changed,
        "skipped": tally.skipped,
        "budget_skipped": tally.budget_skipped,
        "failed": tally.failed,
    }


async def _process_candidate(game_id: int, tally: _BatchTally) -> None:
    with SessionLocal() as db:
        game = db.get(Game, game_id)
        if game is None or not game_needs_metadata_backfill(game):
            tally.skipped += 1
            return
        try:
            result = await refresh_game_metadata(db, game)
        except Exception:
            tally.failed += 1
            log.debug("metadata_backfill_batch failed for game_id=%d", game_id, exc_info=True)
            return
        tally.record(result)
