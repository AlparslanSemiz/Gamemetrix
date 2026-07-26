"""Records the most recent cycle of each periodic background loop.

Every fetching loop wraps its steady-state body in `record_job_run`, which
upserts one `job_runs` row (start → finish) with the run's result counts and the
next-due time. The admin panel reads `latest_job_runs()` to show, per job, when
it last ran, when it is next due, and what that run fetched.

Heartbeat writes are best-effort: a failure here (e.g. the table not yet
migrated) is logged and swallowed so it can never break the actual backfill work
the loop is doing.

Public API:
  JOB_LABELS                                   -> dict[str, str]
  record_job_run(job, interval_seconds)        -> async context manager
  latest_job_runs()                            -> dict[str, dict]
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from ..database import SessionLocal
from ..models import JobRun

log = logging.getLogger(__name__)

# Ordered the way the pipeline runs; the admin panel renders them in this order.
JOB_LABELS: dict[str, str] = {
    "data_fill": "Data Fill (new games + missing data)",
    "rating_refresh": "Score refresh",
    "metadata_backfill": "Metadata backfill",
    "hltb_backfill": "HowLongToBeat playtimes",
    "summary_backfill": "Description audit (AI)",
    "endless_backfill": "Endless classification (AI)",
}


@dataclass
class _RunRecorder:
    """Collects the result the wrapped loop body produced, for the heartbeat."""

    result: dict[str, object] = field(default_factory=dict)

    def set(self, result: dict[str, object]) -> None:
        self.result = dict(result)


def _upsert(
    job: str,
    *,
    status: str,
    interval_seconds: int,
    started_at: datetime,
    finished_at: datetime | None,
    next_run_at: datetime | None,
    result: dict[str, object],
    error: str | None,
) -> None:
    try:
        with SessionLocal() as db:
            row = db.scalar(select(JobRun).where(JobRun.job == job))
            if row is None:
                row = JobRun(job=job)
                db.add(row)
            row.status = status
            row.interval_seconds = interval_seconds
            row.started_at = started_at
            row.finished_at = finished_at
            row.next_run_at = next_run_at
            row.result = result
            row.error = error
            row.updated_at = datetime.now(UTC)
            db.commit()
    except Exception:
        log.debug("Job heartbeat write failed for %s", job, exc_info=True)


@asynccontextmanager
async def record_job_run(job: str, interval_seconds: int) -> AsyncIterator[_RunRecorder]:
    """Upsert a running→finished heartbeat around a loop cycle.

    Yields a recorder whose `set(result)` captures what the cycle fetched.
    Body exceptions are recorded as a failed run and re-raised (the loop's own
    try/except still logs them); heartbeat DB errors are swallowed.
    """
    started = datetime.now(UTC)
    recorder = _RunRecorder()
    _upsert(
        job,
        status="running",
        interval_seconds=interval_seconds,
        started_at=started,
        finished_at=None,
        next_run_at=None,
        result={},
        error=None,
    )
    try:
        yield recorder
    except Exception as exc:
        finished = datetime.now(UTC)
        _upsert(
            job,
            status="failed",
            interval_seconds=interval_seconds,
            started_at=started,
            finished_at=finished,
            next_run_at=finished + timedelta(seconds=interval_seconds),
            result=recorder.result,
            error=type(exc).__name__,
        )
        raise
    finished = datetime.now(UTC)
    _upsert(
        job,
        status="ok",
        interval_seconds=interval_seconds,
        started_at=started,
        finished_at=finished,
        next_run_at=finished + timedelta(seconds=interval_seconds),
        result=recorder.result,
        error=None,
    )


def _serialize(row: JobRun) -> dict[str, object]:
    return {
        "status": row.status,
        "interval_seconds": row.interval_seconds,
        "result": row.result or {},
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def latest_job_runs() -> dict[str, dict[str, object]]:
    """Serialized most-recent run per job that has ever recorded a heartbeat."""
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(JobRun)).all()
    except Exception:
        log.debug("Job heartbeat read failed", exc_info=True)
        return {}
    return {row.job: _serialize(row) for row in rows}


def recover_interrupted_job_runs() -> int:
    """Close heartbeats left in ``running`` state by a backend restart."""
    now = datetime.now(UTC)
    try:
        with SessionLocal() as db:
            result = db.execute(
                update(JobRun)
                .where(JobRun.status == "running")
                .values(
                    status="failed",
                    error="Interrupted by a backend restart.",
                    finished_at=now,
                    next_run_at=now,
                    updated_at=now,
                )
            )
            db.commit()
            return int(result.rowcount or 0)
    except Exception:
        log.debug("Interrupted job heartbeat recovery failed", exc_info=True)
        return 0
