"""IGDB Time-To-Beat playtime backfill.

Only touches games with no playtime yet (and not flagged endless) that have an
IGDB external id. Successful empty responses are cached for 30 days so each run
advances through the catalog instead of querying the same unsupported games.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.igdb_playtime import (
    MAX_IGDB_PLAYTIME_BATCH,
    get_igdb_playtimes_minutes,
)
from ..integrations.rate_limiter import get_rate_limiter
from ..models import ExternalId, Game, SourceSnapshot

log = logging.getLogger(__name__)

_SNAPSHOT_ENDPOINT = "playtime/game-time-to-beats"
_RETRY_AFTER = timedelta(days=30)


def _candidates(db: Session, limit: int) -> list[tuple[int, int]]:
    retry_cutoff = datetime.now(UTC) - _RETRY_AFTER
    checked_recently = exists(
        select(SourceSnapshot.id).where(
            SourceSnapshot.source == "IGDB",
            SourceSnapshot.endpoint == _SNAPSHOT_ENDPOINT,
            SourceSnapshot.external_id == ExternalId.external_id,
            SourceSnapshot.fetched_at >= retry_cutoff,
        )
    )
    rows = db.execute(
        select(Game.id, ExternalId.external_id)
        .join(ExternalId, and_(ExternalId.game_id == Game.id, ExternalId.source == "IGDB"))
        .where(
            Game.content_type == "game",
            Game.playtime_minutes <= 0,
            Game.is_endless.is_(False),
            ~checked_recently,
        )
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc())
        .limit(limit)
    ).all()
    pairs: list[tuple[int, int]] = []
    for game_id, external_id in rows:
        if external_id and str(external_id).isdigit():
            pairs.append((int(game_id), int(external_id)))
    return pairs


def _chunks(
    candidates: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    return [
        candidates[index:index + MAX_IGDB_PLAYTIME_BATCH]
        for index in range(0, len(candidates), MAX_IGDB_PLAYTIME_BATCH)
    ]


def _store_batch(
    candidates: list[tuple[int, int]],
    playtimes: dict[int, int],
) -> tuple[int, int]:
    now = datetime.now(UTC)
    filled = skipped = 0
    with SessionLocal() as db:
        for game_id, igdb_id in candidates:
            minutes = playtimes.get(igdb_id)
            game = db.get(Game, game_id)
            if game is not None and minutes and minutes > 0 and (game.playtime_minutes or 0) <= 0:
                game.playtime_minutes = minutes
                db.add(game)
                filled += 1
            else:
                skipped += 1
            db.add(
                SourceSnapshot(
                    source="IGDB",
                    endpoint=_SNAPSHOT_ENDPOINT,
                    query=None,
                    external_id=str(igdb_id),
                    status_code=200,
                    raw_payload={
                        "found": minutes is not None,
                        "playtime_minutes": minutes,
                    },
                    fetched_at=now,
                    created_at=now,
                )
            )
        db.commit()
    return filled, skipped


async def igdb_playtime_backfill_batch(
    limit: int = 48,
    *,
    inter_game_delay: float = 0.35,
) -> dict[str, int]:
    considered = filled = skipped = failed = 0
    with SessionLocal() as db:
        candidates = _candidates(db, limit)

    for batch in _chunks(candidates):
        if get_rate_limiter().remaining("IGDB") <= 0:
            break
        if not await get_rate_limiter().acquire("IGDB"):
            break
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        try:
            playtimes = await get_igdb_playtimes_minutes(
                [igdb_id for _, igdb_id in batch]
            )
        except Exception:
            log.debug("IGDB playtime backfill batch failed", exc_info=True)
            failed += len(batch)
            continue
        considered += len(batch)
        if playtimes is None:
            failed += len(batch)
            continue
        batch_filled, batch_skipped = _store_batch(batch, playtimes)
        filled += batch_filled
        skipped += batch_skipped

    return {"considered": considered, "filled": filled, "skipped": skipped, "failed": failed}
