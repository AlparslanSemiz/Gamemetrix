"""IGDB Time-To-Beat playtime backfill — fills playtime HLTB could not.

Runs after HLTB: only touches games with no playtime yet (and not flagged
endless) that have an IGDB external id. Sets the source-agnostic
`playtime_minutes` field, never the HLTB-specific columns, so HLTB stays the
primary playtime source and no existing value is overwritten.
"""

import asyncio
import logging

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.igdb_playtime import get_igdb_playtime_minutes
from ..integrations.rate_limiter import get_rate_limiter
from ..models import ExternalId, Game

log = logging.getLogger(__name__)


def _candidates(db: Session, limit: int) -> list[tuple[int, int]]:
    rows = db.execute(
        select(Game.id, ExternalId.external_id)
        .join(ExternalId, and_(ExternalId.game_id == Game.id, ExternalId.source == "IGDB"))
        .where(
            Game.content_type == "game",
            Game.playtime_minutes <= 0,
            Game.is_endless.is_(False),
        )
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc())
        .limit(limit)
    ).all()
    pairs: list[tuple[int, int]] = []
    for game_id, external_id in rows:
        if external_id and str(external_id).isdigit():
            pairs.append((int(game_id), int(external_id)))
    return pairs


async def igdb_playtime_backfill_batch(
    limit: int = 48,
    *,
    inter_game_delay: float = 0.35,
) -> dict[str, int]:
    considered = filled = skipped = failed = 0
    with SessionLocal() as db:
        candidates = _candidates(db, limit)

    for game_id, igdb_id in candidates:
        if get_rate_limiter().remaining("IGDB") <= 0:
            break
        considered += 1
        if not await get_rate_limiter().acquire("IGDB"):
            break
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        try:
            minutes = await get_igdb_playtime_minutes(igdb_id)
        except Exception:
            log.debug("IGDB playtime backfill failed for game_id=%d", game_id, exc_info=True)
            failed += 1
            continue
        if not minutes or minutes <= 0:
            skipped += 1
            continue
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None or (game.playtime_minutes or 0) > 0:
                skipped += 1
                continue
            game.playtime_minutes = minutes
            db.add(game)
            db.commit()
            filled += 1

    return {"considered": considered, "filled": filled, "skipped": skipped, "failed": failed}
