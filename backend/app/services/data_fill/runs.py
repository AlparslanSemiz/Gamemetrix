"""DataFillRun record lifecycle: queue, mark running, finish, serialize."""

from datetime import UTC, datetime

from sqlalchemy import update

from ...database import SessionLocal
from ...models import DataFillRun


def serialize_run(run: DataFillRun | None) -> dict | None:
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


def load_run(run_id: int) -> dict | None:
    with SessionLocal() as db:
        return serialize_run(db.get(DataFillRun, run_id))


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
        return serialize_run(run) or {}


def mark_run_running(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(DataFillRun, run_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        db.commit()


def save_run_progress(run_id: int, result: dict[str, object]) -> None:
    """Persist completed stages so an interrupted run remains diagnosable."""
    with SessionLocal() as db:
        run = db.get(DataFillRun, run_id)
        if run is None or run.status != "running":
            return
        run.result = result
        db.commit()


def recover_interrupted_runs() -> int:
    """Close runs left open by a process restart or container OOM."""
    now = datetime.now(UTC)
    with SessionLocal() as db:
        result = db.execute(
            update(DataFillRun)
            .where(DataFillRun.status.in_(("queued", "running")))
            .values(
                status="failed",
                error="Interrupted before completion by a backend restart.",
                finished_at=now,
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def finish_run(
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
