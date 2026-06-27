"""
Public game endpoints.

Routes:
  GET  /api/search                       — RAWG-backed title search
  GET  /api/games                        — paginated, filtered game list
  GET  /api/games/{slug}                 — single game detail
  POST /api/games/{slug}/refresh-scores  — trigger manual score refresh
  GET  /api/games/{slug}/trailer         — YouTube trailer lookup
  GET  /api/facets                       — genre / year / platform filter options
"""

import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, asc, desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Game, infer_content_type
from ..schemas import (
    FacetsResponse,
    GameListResponse,
    GameRead,
    GameSort,
    SortDirection,
    TrailerResponse,
)
from ..integrations.sync import refresh_game_sources
from ..integrations.youtube import find_trailer_video_id
from ..services.game_filter import (
    dedupe_near_duplicates,
    filter_by_developer,
    filter_by_genre,
    filter_by_max_ratings,
    filter_by_min_ratings,
    filter_by_platform,
    filter_by_publisher,
    filter_has_award,
    filter_has_critic,
    filter_min_live_sources,
    sort_in_memory,
)
from ..services.rawg_import import apply_rawg_to_game, game_from_rawg_search

router = APIRouter(tags=["games"])

_RAWG_SEARCH_TIMEOUT = 15


@router.get("/api/search", response_model=GameRead)
async def search_game(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
) -> Game:
    existing = db.scalar(
        select(Game)
        .where(Game.title.ilike(f"%{q}%"))
        .order_by(Game.metacritic_score.is_(None), desc(Game.metacritic_score))
        .limit(1)
    )
    if existing and existing.metacritic_score is not None:
        return existing

    cfg = get_settings()
    if not cfg.rawg_configured():
        raise HTTPException(
            status_code=400,
            detail="RAWG_API_KEY is not configured. Add it to backend/.env and restart.",
        )

    search_term = existing.title if existing else q
    raw_game = await _fetch_rawg_search(cfg.RAWG_API_KEY, cfg.RAWG_GAMES_URL, search_term)

    game = apply_rawg_to_game(existing, raw_game) if existing else game_from_rawg_search(raw_game)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


async def _fetch_rawg_search(api_key: str, base_url: str, query: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_RAWG_SEARCH_TIMEOUT) as client:
            resp = await client.get(
                base_url,
                params={"key": api_key, "search": query, "page_size": 1},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"RAWG request failed: {exc}") from exc

    results = resp.json().get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="RAWG returned no matching game.")
    return results[0]


@router.get("/api/games", response_model=GameListResponse)
def list_games(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=2),
    genre: str | None = None,
    year_min: int | None = Query(default=None, ge=1970, le=2100),
    year_max: int | None = Query(default=None, ge=1970, le=2100),
    platform: str | None = None,
    content_type: str = Query(default="game"),
    developer: str | None = None,
    publisher: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    min_ratings: int | None = Query(default=None, ge=0),
    max_ratings: int | None = Query(default=None, ge=0),
    min_live_sources: int | None = Query(default=None, ge=0, le=10),
    require_critic: bool = False,
    has_award: bool = False,
    sort: GameSort = "metrix_score",
    direction: SortDirection = "desc",
    limit: int = Query(default=120, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GameListResponse:
    query = _build_db_query(content_type, q, year_min, year_max, min_score, max_score, sort, direction)
    games = list(db.scalars(query).all())
    games = _apply_in_memory_filters(
        games, genre, developer, publisher, platform,
        min_ratings, max_ratings, has_award, min_live_sources, require_critic,
    )
    games = sort_in_memory(games, sort, direction)
    games = dedupe_near_duplicates(games)
    total = len(games)
    return GameListResponse(games=games[offset: offset + limit], total=total)


def _build_db_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    sort: str,
    direction: str,
) -> Select[tuple[Game]]:
    query = select(Game)
    if content_type != "all":
        query = query.where(Game.content_type == content_type)
    if q:
        query = query.where(Game.title.ilike(f"%{q}%"))
    if year_min is not None:
        query = query.where(Game.release_year >= year_min)
    if year_max is not None:
        query = query.where(Game.release_year <= year_max)
    if min_score is not None:
        query = query.where(Game.metrix_score >= min_score)
    if max_score is not None:
        query = query.where(Game.metrix_score <= max_score)
    return _apply_db_sort(query, sort, direction)


def _apply_db_sort(query: Select[tuple[Game]], sort: str, direction: str) -> Select[tuple[Game]]:
    if sort == "title":
        return query.order_by(asc(Game.title))
    if sort == "release_year":
        col = desc(Game.release_year) if direction == "desc" else asc(Game.release_year)
        return query.order_by(col, desc(Game.metrix_score))
    if sort == "critic_score":
        col = desc(Game.critic_score) if direction == "desc" else asc(Game.critic_score)
        return query.order_by(col)
    if sort == "user_score":
        col = desc(Game.user_score) if direction == "desc" else asc(Game.user_score)
        return query.order_by(col)
    col = desc(Game.metrix_score) if direction == "desc" else asc(Game.metrix_score)
    return query.order_by(col)


def _apply_in_memory_filters(
    games: list[Game],
    genre: str | None,
    developer: str | None,
    publisher: str | None,
    platform: str | None,
    min_ratings: int | None,
    max_ratings: int | None,
    has_award: bool,
    min_live_sources: int | None,
    require_critic: bool,
) -> list[Game]:
    if genre:
        games = filter_by_genre(games, genre)
    if developer:
        games = filter_by_developer(games, developer)
    if publisher:
        games = filter_by_publisher(games, publisher)
    if platform:
        games = filter_by_platform(games, platform)
    if min_ratings:
        games = filter_by_min_ratings(games, min_ratings)
    if max_ratings:
        games = filter_by_max_ratings(games, max_ratings)
    if has_award:
        games = filter_has_award(games)
    if min_live_sources:
        games = filter_min_live_sources(games, min_live_sources)
    if require_critic:
        games = filter_has_critic(games)
    return games


@router.get("/api/games/{slug}", response_model=GameRead)
def get_game(slug: str, db: Session = Depends(get_db)) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/api/games/{slug}/refresh-scores", response_model=GameRead)
async def refresh_game_scores(slug: str, db: Session = Depends(get_db)) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return await refresh_game_sources(db, game)


@router.get("/api/games/{slug}/trailer", response_model=TrailerResponse)
async def get_trailer(slug: str, db: Session = Depends(get_db)) -> dict[str, str | None]:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    video_id = await find_trailer_video_id(game.title)
    return {
        "video_id": video_id,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


@router.get("/api/facets", response_model=FacetsResponse)
def get_facets(db: Session = Depends(get_db)) -> FacetsResponse:
    current_year = datetime.date.today().year
    games = db.scalars(select(Game).where(Game.content_type == "game")).all()

    genres = sorted({genre for g in games for genre in g.genres})
    years = sorted(
        {g.release_year for g in games if g.release_year <= current_year},
        reverse=True,
    )
    raw_platforms = {p for g in games for p in g.platforms}
    return FacetsResponse(
        genres=genres,
        years=years,
        platforms=sorted(_build_platform_filters(raw_platforms)),
    )


def _build_platform_filters(platforms: set[str]) -> set[str]:
    filters = set(platforms)
    if any(p in platforms for p in ("PC", "Steam")):
        filters.add("Steam")
    if any("PlayStation" in p for p in platforms):
        filters.add("PlayStation")
    if any("Xbox" in p for p in platforms):
        filters.add("Xbox")
    if any(p in platforms for p in ("Nintendo Switch", "Nintendo", "Wii", "Wii U")):
        filters.add("Nintendo")
    return filters
