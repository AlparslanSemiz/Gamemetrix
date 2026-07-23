"""Admin RAWG-backed title search that imports the match into the catalog."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import get_db
from ...integrations.rate_limiter import get_rate_limiter
from ...models import Game
from ...rate_limit import limiter
from ...schemas import GameRead
from ...security import require_admin_user
from ...services.deduplication import find_existing_duplicate, merge_game_data
from ...services.game_filter import LIKE_ESCAPE_CHAR, escape_like
from ...services.rawg_import import apply_rawg_to_game, game_from_rawg_search

router = APIRouter()

_RAWG_SEARCH_TIMEOUT = 15


@router.get("/api/search", response_model=GameRead)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def search_game(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    existing = _best_local_match(db, q)
    if existing and existing.metacritic_score is not None:
        return existing

    cfg = get_settings()
    if not cfg.rawg_configured():
        raise HTTPException(
            status_code=400,
            detail="RAWG_API_KEY is not configured. Add it to backend/.env and restart.",
        )
    if not await get_rate_limiter().acquire("RAWG"):
        raise HTTPException(status_code=429, detail="RAWG request budget is exhausted.")

    raw_game = await _fetch_rawg_search(
        cfg.RAWG_API_KEY, cfg.RAWG_GAMES_URL, existing.title if existing else q
    )
    game = apply_rawg_to_game(existing, raw_game) if existing else game_from_rawg_search(raw_game)
    if existing is None:
        game = _merge_into_duplicate(db, game)

    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _best_local_match(db: Session, q: str) -> Game | None:
    return db.scalar(
        select(Game)
        .where(Game.title.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE_CHAR))
        .order_by(Game.metacritic_score.is_(None), desc(Game.metacritic_score))
        .limit(1)
    )


def _merge_into_duplicate(db: Session, game: Game) -> Game:
    duplicate = find_existing_duplicate(db, game)
    if duplicate is None:
        return game
    merge_game_data(duplicate, game)
    return duplicate


async def _fetch_rawg_search(api_key: str, base_url: str, query: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_RAWG_SEARCH_TIMEOUT) as client:
            resp = await client.get(
                base_url,
                params={"key": api_key, "search": query, "page_size": 1},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"RAWG returned HTTP {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"RAWG request failed ({type(exc).__name__})."
        ) from exc

    results = resp.json().get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="RAWG returned no matching game.")
    return results[0]
