"""Weekly ProtonDB refresh: writes `proton_tier`, `proton_score`, `proton_refreshed_at`.

Only games whose Steam app id was verified against appdetails are queried, so a
wrong id can never hand a game another title's Linux verdict. The Linux filter
counts Proton-playable tiers next to native builds, which makes this data user-facing.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..integrations.protondb import ProtonSummary, fetch_proton_summary
from ..models import Game
from .job_heartbeat import record_job_run

log = logging.getLogger(__name__)

# ProtonDB documents no quota; one request per second at most is the self-imposed ceiling.
MIN_DELAY_SECONDS = 1.0
_CONSECUTIVE_ERROR_LIMIT = 5

SummaryFetcher = Callable[[int], Awaitable[ProtonSummary]]


def proton_refresh_candidates(db: Session, *, limit: int, max_age: timedelta) -> list[Game]:
    """Verified-id PC games whose Proton data is missing or older than `max_age`."""
    cutoff = datetime.now(UTC) - max_age
    return list(db.scalars(
        select(Game)
        .where(
            Game.content_type == "game",
            Game.steam_app_id.is_not(None),
            Game.steam_app_id_verified_at.is_not(None),
            or_(Game.proton_refreshed_at.is_(None), Game.proton_refreshed_at < cutoff),
        )
        .order_by(Game.proton_refreshed_at.asc().nulls_first(), Game.rank_score.desc(), Game.id)
        .limit(limit)
    ).all())


async def refresh_proton_tiers(
    db: Session,
    *,
    limit: int,
    delay_seconds: float,
    max_age: timedelta = timedelta(days=7),
    fetcher: SummaryFetcher | None = None,
) -> dict[str, int]:
    delay = max(MIN_DELAY_SECONDS, delay_seconds)
    updated = unchanged = no_reports = errors = 0
    owned: httpx.AsyncClient | None = None
    if fetcher is None:
        owned = httpx.AsyncClient()
        client = owned

        async def fetcher(app_id: int) -> ProtonSummary:  # noqa: F811
            return await fetch_proton_summary(app_id, client)

    consecutive_errors = 0
    try:
        for index, game in enumerate(proton_refresh_candidates(db, limit=limit, max_age=max_age)):
            if index:
                await asyncio.sleep(delay)
            summary = await fetcher(int(game.steam_app_id or 0))
            if summary.status == "error":
                errors += 1
                consecutive_errors += 1
                if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                    break
                continue
            consecutive_errors = 0
            if summary.status == "ok":
                if (game.proton_tier, game.proton_score) == (summary.tier, summary.score):
                    unchanged += 1
                else:
                    game.proton_tier, game.proton_score = summary.tier, summary.score
                    updated += 1
            else:
                no_reports += 1
            game.proton_refreshed_at = datetime.now(UTC)
            db.add(game)
            if (index + 1) % 50 == 0:
                db.commit()
        db.commit()
    finally:
        if owned is not None:
            await owned.aclose()
    return {"updated": updated, "unchanged": unchanged, "no_reports": no_reports, "errors": errors}


async def protondb_refresh_loop() -> None:
    """Runs forever: one bounded batch per interval (default weekly cadence, daily batches)."""
    cfg = get_settings()
    if not cfg.PROTONDB_REFRESH_ENABLED:
        return
    await asyncio.sleep(180)
    # Batches run daily and each game is revisited at most weekly, so the whole
    # verified catalog rotates through without one huge burst.
    interval_seconds = max(3600, int(min(cfg.PROTONDB_REFRESH_INTERVAL_HOURS, 24) * 3600))
    max_age = timedelta(hours=cfg.PROTONDB_REFRESH_INTERVAL_HOURS)
    while True:
        try:
            async with record_job_run("protondb_refresh", interval_seconds) as run:
                # No HEAVY_JOB_LOCK: the batch mostly sleeps between requests and
                # touches one row at a time, so it must not block imports.
                with SessionLocal() as db:
                    run.set(await refresh_proton_tiers(
                        db,
                        limit=cfg.PROTONDB_REFRESH_BATCH_SIZE,
                        delay_seconds=cfg.PROTONDB_REQUEST_DELAY_SECONDS,
                        max_age=max_age,
                    ))
        except Exception:
            log.exception("ProtonDB refresh failed")
        await asyncio.sleep(interval_seconds)
