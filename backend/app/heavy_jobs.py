"""
Shared safeguards for admin-triggered bulk jobs — RAWG/IGDB/etc. catalog
imports and the full ratings refresh — that each fan out many outbound HTTP
calls. On a 1GB host, two of these running at once is enough to trip the
OOM killer, so:

  HEAVY_JOB_LOCK      — one shared asyncio.Lock across every heavy job.
                        Imports and services.background.refresh_all_games()
                        both acquire this SAME lock, so an import and a
                        refresh-all can never run concurrently, and two
                        overlapping triggers fail fast (429) instead of
                        silently doubling the load.
  require_not_peak_hours — optional dependency that rejects new heavy jobs
                        during a configured window (e.g. evening peak
                        traffic) unless the caller passes
                        override_peak_hours=true.
  require_heavy_job_slot — yield-dependency for endpoints that run the job
                        inline (imports): holds HEAVY_JOB_LOCK for the
                        request's duration.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, time

from fastapi import HTTPException, Query

from .config import get_settings

HEAVY_JOB_LOCK = asyncio.Lock()


def _in_peak_window(now_time: time, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return False  # feature disabled
    start, end = time(start_hour), time(end_hour)
    if start < end:
        return start <= now_time < end
    return now_time >= start or now_time < end  # window wraps past midnight


async def require_not_peak_hours(override_peak_hours: bool = Query(default=False)) -> None:
    if override_peak_hours:
        return
    cfg = get_settings()
    if _in_peak_window(datetime.now().time(), cfg.HEAVY_JOB_BLOCK_START_HOUR, cfg.HEAVY_JOB_BLOCK_END_HOUR):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Heavy jobs are paused {cfg.HEAVY_JOB_BLOCK_START_HOUR:02d}:00-"
                f"{cfg.HEAVY_JOB_BLOCK_END_HOUR:02d}:00 to protect the host during peak traffic. "
                "Pass override_peak_hours=true to run anyway."
            ),
        )


async def require_heavy_job_slot() -> AsyncIterator[None]:
    if HEAVY_JOB_LOCK.locked():
        raise HTTPException(
            status_code=429,
            detail="Another heavy job (import or ratings refresh) is already running. Try again shortly.",
        )
    async with HEAVY_JOB_LOCK:
        yield
