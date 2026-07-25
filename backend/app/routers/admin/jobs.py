"""Heavy background jobs: catalog data fill, primary-score backfill, consolidation."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import Settings, get_settings
from ...content_type import infer_content_type_with_parent
from ...database import SessionLocal, get_db
from ...heavy_jobs import HEAVY_JOB_LOCK
from ...models import Game
from ...services.data_fill import data_fill_status, execute_data_fill_run, queue_data_fill_run
from ...services.deduplication import consolidate_duplicate_games, preview_duplicate_groups
from ...services.job_heartbeat import JOB_LABELS, latest_job_runs
from ...services.primary_score_backfill import (
    primary_score_backfill_batch,
    primary_score_coverage_status,
)
from ...services.seo import refresh_catalog_seo_states

router = APIRouter()


def _job_schedule(cfg: Settings) -> dict[str, int]:
    """Configured interval, in seconds, for each tracked periodic loop."""
    return {
        "data_fill": int(cfg.DATA_FILL_INTERVAL_HOURS * 3600),
        "rating_refresh": int(cfg.REFRESH_ALL_INTERVAL_HOURS * 3600),
        "metadata_backfill": int(cfg.METADATA_BACKFILL_INTERVAL_MINUTES * 60),
        "hltb_backfill": int(cfg.HLTB_BACKFILL_INTERVAL_MINUTES * 60),
        "summary_backfill": int(cfg.SUMMARY_SHORTEN_INTERVAL_MINUTES * 60),
        "endless_backfill": int(cfg.ENDLESS_BACKFILL_INTERVAL_MINUTES * 60),
    }


def _ai_status(cfg: Settings) -> dict[str, object]:
    configured = cfg.groq_configured()
    return {
        "provider": "Groq",
        "model": cfg.GROQ_MODEL,
        "configured": configured,
        "uses": {
            "summary_rewrite": configured,
            "catalog_quality_review": configured,
            "catalog_quality_repair_verification": configured,
            "endless_classification": cfg.ENDLESS_USE_AI and configured,
            "similar_games_rerank": cfg.SIMILARITY_USE_AI and configured,
        },
    }


@router.get("/jobs/periodic")
def get_periodic_jobs() -> dict[str, object]:
    """Per-loop last run, next-due time, and what the last run fetched."""
    cfg = get_settings()
    schedule = _job_schedule(cfg)
    runs = latest_job_runs()
    jobs: list[dict[str, object]] = []
    for job, label in JOB_LABELS.items():
        run = runs.get(job, {})
        enabled = cfg.DATA_FILL_ENABLED if job == "data_fill" else True
        jobs.append({
            "job": job,
            "label": label,
            "enabled": enabled,
            "interval_seconds": run.get("interval_seconds") or schedule.get(job, 0),
            "status": run.get("status", "never"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "next_run_at": run.get("next_run_at"),
            "result": run.get("result", {}),
            "error": run.get("error"),
        })
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "ai": _ai_status(cfg),
        "jobs": jobs,
    }

_DEFAULT_JOB_TARGET = 50000
_MAX_JOB_TARGET = 250000
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
