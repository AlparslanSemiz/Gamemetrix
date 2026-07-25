"""Runs every fill stage in order under the heavy-job lock, recording the result."""

import asyncio
import logging

from ...config import get_settings
from ...database import SessionLocal
from ...heavy_jobs import HEAVY_JOB_LOCK
from ..job_heartbeat import record_job_run
from ..seo import refresh_catalog_seo_states
from .runs import finish_run, load_run, mark_run_running, queue_data_fill_run
from .stages import (
    audit_catalog_quality,
    fill_catalog,
    fill_endless,
    fill_hltb,
    fill_igdb_playtime,
    fill_metacritic,
    fill_metadata,
    fill_prices,
    fill_primary_scores,
    fill_ratings,
    fill_summaries,
    repair_catalog_quality,
)
from .status import count_missing_external_ids

log = logging.getLogger(__name__)

_BUSY_RETRY_SECONDS = 5 * 60
_MIN_LOOP_INTERVAL_SECONDS = 3600
_SECONDS_PER_HOUR = 3600

_EMPTY_RESULT: dict[str, object] = {
    "catalog": {},
    "quality": {},
    "repairs": {},
    "metacritic": {},
    "ratings": {},
    "primary_scores": {},
    "metadata": {},
    "hltb": {},
    "igdb_playtime": {},
    "endless": {},
    "summaries": {},
    "prices": {},
    "completeness": {},
    "external_ids": {},
}


async def execute_data_fill_run(run_id: int, *, force: bool, target_total: int) -> None:
    if HEAVY_JOB_LOCK.locked():
        finish_run(run_id, status="skipped", error="Another heavy job is already running.")
        return

    async with HEAVY_JOB_LOCK:
        mark_run_running(run_id)
        result = dict(_EMPTY_RESULT)
        try:
            await _run_all_stages(result, force=force, target_total=target_total)
            finish_run(run_id, status="complete", result=result)
        except Exception as exc:
            log.error("Data fill run failed (%s)", type(exc).__name__)
            finish_run(
                run_id,
                status="failed",
                result=result,
                error=f"Data fill failed ({type(exc).__name__}). Check server logs.",
            )


async def _run_all_stages(
    result: dict[str, object],
    *,
    force: bool,
    target_total: int,
) -> None:
    before_missing = count_missing_external_ids()
    result["external_ids"] = {"before_missing": before_missing}

    result["catalog"] = await fill_catalog(target_total)
    result["quality"] = await audit_catalog_quality()
    result["repairs"] = await repair_catalog_quality()
    result["metacritic"] = await fill_metacritic()
    result["primary_scores"] = await fill_primary_scores(force=force)
    result["ratings"] = await fill_ratings(force=force)
    result["metadata"] = await fill_metadata()
    result["hltb"] = await fill_hltb()
    result["igdb_playtime"] = await fill_igdb_playtime()
    result["endless"] = await fill_endless()
    result["summaries"] = await fill_summaries()
    result["prices"] = await fill_prices()

    result["completeness"] = _sweep_completeness()
    result["seo"] = _refresh_seo()
    result["external_ids"] = _external_id_summary(before_missing)


def _sweep_completeness() -> dict[str, object]:
    from ..completeness import sweep_data_complete

    with SessionLocal() as db:
        return sweep_data_complete(db)


def _refresh_seo() -> dict[str, object]:
    with SessionLocal() as db:
        summary = refresh_catalog_seo_states(db)
        db.commit()
        return summary


def _external_id_summary(before_missing: int) -> dict[str, int]:
    after_missing = count_missing_external_ids()
    return {
        "before_missing": before_missing,
        "after_missing": after_missing,
        "matched": max(0, before_missing - after_missing),
    }


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _stage(result: dict[str, object], key: str) -> dict[str, object]:
    stage = result.get(key)
    return stage if isinstance(stage, dict) else {}


def _data_fill_summary(result: dict[str, object]) -> dict[str, int]:
    """Flatten the rich per-stage run result into the counts that matter for the
    periodic-jobs panel: what this cycle actually added or refreshed."""
    return {
        "catalog_total": _int(_stage(result, "catalog").get("total_games")),
        "metacritic_seeded": _int(_stage(result, "metacritic").get("seeded")),
        "scores_refreshed": _int(_stage(result, "ratings").get("refreshed")),
        "metadata_enriched": _int(_stage(result, "metadata").get("enriched")),
        "hltb_imported": _int(_stage(result, "hltb").get("imported")),
        "igdb_playtime_filled": _int(_stage(result, "igdb_playtime").get("filled")),
        "prices_stored": _int(_stage(result, "prices").get("stored")),
        "summaries_shortened": _int(_stage(result, "summaries").get("shortened")),
        "endless_flagged": _int(_stage(result, "endless").get("endless")),
        "quality_ai_checked": _int(_stage(result, "quality").get("ai_checked")),
        "quality_needs_review": _int(_stage(result, "quality").get("needs_review")),
        "quality_quarantined": _int(_stage(result, "quality").get("quarantined")),
        "quality_repaired": _int(_stage(result, "repairs").get("repaired")),
        "external_ids_matched": _int(_stage(result, "external_ids").get("matched")),
    }


async def data_fill_loop() -> None:
    cfg = get_settings()
    if not cfg.DATA_FILL_ENABLED:
        return

    interval_seconds = max(
        _MIN_LOOP_INTERVAL_SECONDS, int(cfg.DATA_FILL_INTERVAL_HOURS * _SECONDS_PER_HOUR)
    )
    await asyncio.sleep(max(0, cfg.DATA_FILL_STARTUP_DELAY_SECONDS))
    while True:
        if HEAVY_JOB_LOCK.locked():
            await asyncio.sleep(_BUSY_RETRY_SECONDS)
            continue
        async with record_job_run("data_fill", interval_seconds) as heartbeat:
            run = queue_data_fill_run(force=False, target_total=cfg.DATA_FILL_TARGET_TOTAL)
            await execute_data_fill_run(
                int(run["id"]), force=False, target_total=cfg.DATA_FILL_TARGET_TOTAL
            )
            finished = load_run(int(run["id"]))
            if finished:
                heartbeat.set(_data_fill_summary(finished.get("result") or {}))
        await asyncio.sleep(interval_seconds)
