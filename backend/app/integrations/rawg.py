import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Game
from ..services.rawg_import import game_from_rawg_list


log = logging.getLogger(__name__)

_RAWG_LIST_URL = "https://api.rawg.io/api/games"
_HTTP_TIMEOUT = 20


async def import_rawg_games(db: Session, target: int = 2000, page_size: int = 40) -> dict[str, int]:
    cfg = get_settings()
    if not cfg.rawg_configured():
        raise RuntimeError("RAWG_API_KEY is not configured.")

    imported = 0
    skipped = 0
    page = 1

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        while imported < target:
            response = await client.get(
                _RAWG_LIST_URL,
                params={
                    "key": cfg.RAWG_API_KEY,
                    "page": page,
                    "page_size": min(page_size, target - imported),
                    "ordering": "-metacritic,-rating",
                },
            )
            response.raise_for_status()
            results = response.json().get("results", [])

            if not results:
                break

            for raw_game in results:
                game = game_from_rawg_list(raw_game)
                existing = db.scalar(select(Game).where(Game.slug == game.slug))
                if existing:
                    skipped += 1
                    continue

                db.add(game)
                imported += 1

            db.commit()
            page += 1

    return {"imported": imported, "skipped": skipped}
