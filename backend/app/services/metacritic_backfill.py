"""CheapShark Metacritic backfill — seeds game.metacritic_score for PC games.

CheapShark (free, no key) returns a real Metacritic score in its deal payload.
Seeding it here fills the Metacritic cache so the periodic score refresh produces
a live Metacritic without spending RAWG's scarce monthly budget. RAWG stays the
fallback for games CheapShark doesn't cover (console-only titles, non-store PC
games), so no existing path is removed.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.types import bounded_float
from ..models import Game

log = logging.getLogger(__name__)

_MIN_METACRITIC = 1
_MAX_METACRITIC = 100
_SEARCH_LIMIT = 10


def _metacritic_from_deals(deals: list[dict]) -> int | None:
    for deal in deals:
        value = bounded_float(deal.get("metacriticScore"), maximum=float(_MAX_METACRITIC))
        if value is not None and _MIN_METACRITIC <= value <= _MAX_METACRITIC:
            return int(round(value))
    return None


def metacritic_backfill_candidates(db: Session, limit: int) -> list[int]:
    return list(
        db.scalars(
            select(Game.id)
            .where(Game.content_type == "game", Game.metacritic_score.is_(None))
            .order_by(Game.rank_score.desc(), Game.metrix_score.desc())
            .limit(limit)
        ).all()
    )


async def cheapshark_metacritic_backfill_batch(
    limit: int = 48,
    *,
    inter_game_delay: float = 0.35,
) -> dict[str, int]:
    considered = seeded = skipped = failed = 0
    with SessionLocal() as db:
        candidate_ids = metacritic_backfill_candidates(db, limit)

    for game_id in candidate_ids:
        if get_rate_limiter().remaining("CheapShark") <= 0:
            break
        considered += 1
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None or not game.is_pc_applicable:
                skipped += 1
                continue
            try:
                deals = await cheapshark_service.search_deals(game.title, limit=_SEARCH_LIMIT)
                value = _metacritic_from_deals(deals) if deals else None
            except Exception:
                log.debug("CheapShark Metacritic backfill failed for game_id=%d", game_id, exc_info=True)
                failed += 1
                continue
            if value is None:
                skipped += 1
                continue
            game.metacritic_score = value
            db.add(game)
            db.commit()
            seeded += 1

    return {"considered": considered, "seeded": seeded, "skipped": skipped, "failed": failed}
