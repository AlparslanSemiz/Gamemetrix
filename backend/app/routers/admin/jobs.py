"""Heavy background jobs: catalog data fill, primary-score backfill, consolidation."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...content_type import infer_content_type_with_parent
from ...database import SessionLocal, get_db
from ...heavy_jobs import HEAVY_JOB_LOCK
from ...models import Game
from ...services.data_fill import data_fill_status, execute_data_fill_run, queue_data_fill_run
from ...services.deduplication import consolidate_duplicate_games, preview_duplicate_groups
from ...services.primary_score_backfill import (
    primary_score_backfill_batch,
    primary_score_coverage_status,
)
from ...services.seo import refresh_catalog_seo_states

router = APIRouter()

_DEFAULT_JOB_TARGET = 10000
_MAX_JOB_TARGET = 100000
_HEAVY_JOB_BUSY = "Another heavy job is already running."


def _reject_if_busy() -> None:
    if HEAVY_JOB_LOCK.locked():
        raise HTTPException(status_code=409, detail=_HEAVY_JOB_BUSY)


@router.get("/data-fill/status")
def get_data_fill_status() -> dict[str, object]:
    return data_fill_status()


@router.post("/data-fill/run")
async def run_data_fill(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    target_total: int = Query(default=_DEFAULT_JOB_TARGET, ge=1, le=_MAX_JOB_TARGET),
) -> dict[str, object]:
    _reject_if_busy()
    run = queue_data_fill_run(force=force, target_total=target_total)
    background_tasks.add_task(
        execute_data_fill_run,
        int(run["id"]),
        force=force,
        target_total=target_total,
    )
    return {"status": "queued", "run": run}


@router.get("/primary-scores/status")
def get_primary_scores_status() -> dict[str, object]:
    return primary_score_coverage_status()


@router.post("/primary-scores/run")
async def run_primary_scores(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    limit: int = Query(default=_DEFAULT_JOB_TARGET, ge=1, le=_MAX_JOB_TARGET),
) -> dict[str, object]:
    _reject_if_busy()
    background_tasks.add_task(_execute_primary_scores_run, force=force, limit=limit)
    return {"status": "started", "coverage": primary_score_coverage_status()}


async def _execute_primary_scores_run(*, force: bool, limit: int) -> None:
    if HEAVY_JOB_LOCK.locked():
        return
    cfg = get_settings()
    async with HEAVY_JOB_LOCK:
        result = await primary_score_backfill_batch(
            limit=limit,
            force=force,
            inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
        )
        if int(result.get("refreshed_games", 0)):
            with SessionLocal() as db:
                refresh_catalog_seo_states(db)
                db.commit()


@router.post("/consolidate")
def admin_consolidate(
    dry_run: bool = Query(default=False, description="Report what would merge without writing."),
    db: Session = Depends(get_db),
) -> dict:
    """Reclassify games by inferred content_type, then merge duplicate rows."""
    if dry_run:
        groups = preview_duplicate_groups(db)
        return {
            "dry_run": True,
            "groups": groups,
            "merged_groups": len(groups),
            "removed": sum(len(group["duplicates"]) for group in groups),
        }

    reclassified = _reclassify_content_types(db)
    result = consolidate_duplicate_games(db)
    return {
        "reclassified": reclassified,
        "merged_groups": result["merged_groups"],
        "removed": result["removed"],
    }


def _reclassify_content_types(db: Session) -> int:
    all_games = list(db.scalars(select(Game)).all())
    parent_titles = frozenset(game.title.strip().lower() for game in all_games)
    reclassified = 0
    for game in all_games:
        inferred = infer_content_type_with_parent(game, parent_titles)
        if game.content_type != inferred:
            game.content_type = inferred
            reclassified += 1
    if reclassified:
        db.commit()
    return reclassified
