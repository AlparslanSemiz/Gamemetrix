"""
Public game endpoints.

Routes:
  GET  /api/search                          — admin RAWG-backed title search/import
  GET  /api/games                           — paginated, filtered game list
  GET  /api/games/{slug}                    — single game detail
  POST /api/games/{slug}/refresh-scores     — trigger manual score refresh
  POST /api/games/{slug}/fetch-screenshots  — fetch & store Steam screenshots
  POST /api/games/{slug}/fetch-prices       — fetch & store current price/deal data
  GET  /api/games/{slug}/trailer            — YouTube trailer lookup
  GET  /api/facets                          — genre / year / platform filter options
"""

import datetime
import logging
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, noload, selectinload

from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import Game
from ..schemas import (
    FacetsResponse,
    GameListResponse,
    GameRead,
    GameSort,
    SeriesResponse,
    SortDirection,
    TrailerResponse,
)
from ..integrations.steam import (
    extract_steam_app_id,
    fetch_steam_screenshots,
    fetch_steam_system_requirements,
)
from ..integrations.sync import refresh_game_sources
from ..services.game_filter import (
    LIKE_ESCAPE_CHAR,
    escape_like,
)
from ..services.game_query import (
    CatalogFilters,
    apply_advanced_filters,
    build_catalog_count_query,
    build_catalog_query,
    build_platform_filters,
    json_array_values_statement,
)
from ..services.deduplication import find_existing_duplicate, merge_game_data
from ..services.game_similarity import find_series_games, find_similar_games, series_key_for_title
from ..services.metadata_backfill import game_needs_metadata_backfill, refresh_game_metadata
from ..services.price_backfill import fetch_and_store_prices
from ..services.rawg_import import apply_rawg_to_game, game_from_rawg_search
from ..services.seo import refresh_catalog_seo_states
from ..services.trailer_cache import cached_trailer_video_id
from ..rate_limit import limiter
from ..integrations.rate_limiter import get_rate_limiter
from ..security import AuthenticatedUser, optional_admin_user, require_admin_user

router = APIRouter(tags=["games"])
log = logging.getLogger(__name__)

_RAWG_SEARCH_TIMEOUT = 15
ContentTypeFilter = Literal["all", "game", "dlc", "demo", "mod", "software", "soundtrack", "utility"]
DealFilter = Literal["all", "best", "free"]
PlayerModeFilter = Literal["singleplayer", "multiplayer", "coop"]
SlugPath = Annotated[str, Path(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


def _get_game_or_404(db: Session, slug: str) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("/api/search", response_model=GameRead)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def search_game(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    existing = db.scalar(
        select(Game)
        .where(Game.title.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE_CHAR))
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
    if not await get_rate_limiter().acquire("RAWG"):
        raise HTTPException(status_code=429, detail="RAWG request budget is exhausted.")
    raw_game = await _fetch_rawg_search(cfg.RAWG_API_KEY, cfg.RAWG_GAMES_URL, search_term)

    game = apply_rawg_to_game(existing, raw_game) if existing else game_from_rawg_search(raw_game)
    if existing is None:
        duplicate = find_existing_duplicate(db, game)
        if duplicate:
            merge_game_data(duplicate, game)
            game = duplicate
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
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"RAWG returned HTTP {exc.response.status_code}.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"RAWG request failed ({type(exc).__name__}).") from exc

    results = resp.json().get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="RAWG returned no matching game.")
    return results[0]


@router.get("/api/games", response_model=GameListResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def list_games(
    request: Request,
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=2, max_length=120),
    genre: str | None = Query(default=None, max_length=80),
    year_min: int | None = Query(default=None, ge=1970, le=2100),
    year_max: int | None = Query(default=None, ge=1970, le=2100),
    platform: str | None = Query(default=None, max_length=80),
    content_type: ContentTypeFilter = Query(default="game"),
    developer: str | None = Query(default=None, max_length=200),
    publisher: str | None = Query(default=None, max_length=200),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    min_ratings: int | None = Query(default=None, ge=0, le=2_000_000_000),
    max_ratings: int | None = Query(default=None, ge=0, le=2_000_000_000),
    min_live_sources: int | None = Query(default=None, ge=0, le=10),
    player_mode: PlayerModeFilter | None = Query(default=None),
    playtime_min_hours: float | None = Query(default=None, ge=0, le=1000),
    playtime_max_hours: float | None = Query(default=None, ge=0, le=1000),
    require_critic: bool = False,
    has_award: bool = False,
    deal: DealFilter = Query(default="all"),
    sort: GameSort = "rank_score",
    direction: SortDirection = "desc",
    limit: int = Query(default=120, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> GameListResponse:
    advanced = CatalogFilters(
        genre=genre,
        developer=developer,
        publisher=publisher,
        platform=platform,
        min_ratings=min_ratings,
        max_ratings=max_ratings,
        has_award=has_award,
        min_live_sources=min_live_sources,
        require_critic=require_critic,
        player_mode=player_mode,
        playtime_min_hours=playtime_min_hours,
        playtime_max_hours=playtime_max_hours,
    )
    base_q = apply_advanced_filters(
        build_catalog_query(content_type, q, year_min, year_max, min_score, max_score, deal, sort, direction),
        advanced,
    )
    count_q = apply_advanced_filters(
        build_catalog_count_query(content_type, q, year_min, year_max, min_score, max_score, deal),
        advanced,
    )
    price_options = selectinload(Game.price_snapshots) if deal != "all" else noload(Game.price_snapshots)

    total = db.scalar(count_q) or 0
    page_q = base_q.options(price_options).offset(offset).limit(limit)
    games = list(db.scalars(page_q).all())
    return GameListResponse(games=games, total=total)


@router.get("/api/games/{slug}", response_model=GameRead)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def get_game(
    request: Request,
    slug: SlugPath,
    background_tasks: BackgroundTasks,
    refresh_metadata: bool = Query(default=False, alias="refresh"),
    db: Session = Depends(get_db),
    admin: AuthenticatedUser | None = Depends(optional_admin_user),
) -> Game:
    game = _get_game_or_404(db, slug)
    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)
    needs_refresh = game_needs_metadata_backfill(game) or (
        app_id and _system_requirements_need_repair(game.system_requirements)
    )
    if refresh_metadata and admin is None:
        raise HTTPException(status_code=403, detail="Admin role required to refresh metadata.")
    if refresh_metadata and needs_refresh:
        background_tasks.add_task(_refresh_game_detail_metadata, game.slug)
    return game


async def _refresh_game_detail_metadata(slug: str) -> None:
    """Best-effort metadata backfill that keeps the detail endpoint responsive."""
    with SessionLocal() as db:
        game = db.scalar(select(Game).where(Game.slug == slug))
        if game is None:
            return
        try:
            await refresh_game_metadata(db, game)
        except Exception:
            log.debug("Detail metadata backfill failed for %s", slug, exc_info=True)


_BAD_SYSTEM_REQUIREMENT_MARKERS = (
    "windows xp",
    "1.2ghz",
    "256mb",
    "250 mb",
)


def _system_requirements_need_repair(requirements: list[dict] | None) -> bool:
    if not requirements:
        return True
    pc_req = next(
        (req for req in requirements if str(req.get("platform", "")).lower() in {"pc", "windows"}),
        requirements[0],
    )
    text = " ".join(
        str(pc_req.get(key) or "")
        for key in ("minimum", "recommended")
    ).lower()
    if not text.strip():
        return True
    if any(marker in text for marker in _BAD_SYSTEM_REQUIREMENT_MARKERS):
        return True
    return False


@router.get("/api/games/{slug}/similar", response_model=GameListResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def get_similar_games(
    request: Request,
    slug: SlugPath,
    limit: int = Query(default=10, ge=1, le=24),
    db: Session = Depends(get_db),
) -> GameListResponse:
    game = _get_game_or_404(db, slug)
    similar = find_similar_games(db, game, display_limit=limit)
    return GameListResponse(games=similar, total=len(similar))


@router.get("/api/games/{slug}/series", response_model=SeriesResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def get_series_games(
    request: Request,
    slug: SlugPath,
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
) -> SeriesResponse:
    """Other games in the same franchise (e.g. Persona 5 Royal → other Persona games), oldest first."""
    game = _get_game_or_404(db, slug)
    series = find_series_games(db, game, limit=limit)
    return SeriesResponse(
        series_key=series_key_for_title(game.title),
        games=series,
        total=len(series),
    )


@router.post("/api/games/{slug}/refresh-scores", response_model=GameRead)
async def refresh_game_scores(
    slug: SlugPath,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    game = _get_game_or_404(db, slug)
    refreshed = await refresh_game_sources(db, game)
    refresh_catalog_seo_states(db)
    db.commit()
    db.refresh(refreshed)
    return refreshed


@router.post("/api/games/{slug}/fetch-screenshots", response_model=GameRead)
async def fetch_game_screenshots(
    slug: SlugPath,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    game = _get_game_or_404(db, slug)

    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)
    if app_id is None:
        raise HTTPException(status_code=422, detail="No Steam App ID found for this game.")

    screenshots = await fetch_steam_screenshots(app_id)
    if screenshots:
        game.screenshots = screenshots
        db.commit()
        db.refresh(game)

    return game


@router.post("/api/games/{slug}/fetch-system-requirements", response_model=GameRead)
async def fetch_game_system_requirements(
    slug: SlugPath,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    game = _get_game_or_404(db, slug)

    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)
    if app_id is None:
        raise HTTPException(status_code=422, detail="No Steam App ID found for this game.")

    requirements = await fetch_steam_system_requirements(app_id)
    if requirements:
        game.system_requirements = requirements
        db.commit()
        db.refresh(game)

    return game


@router.post("/api/games/{slug}/fetch-prices", response_model=GameRead)
async def fetch_game_prices(
    slug: SlugPath,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> Game:
    game = _get_game_or_404(db, slug)

    await fetch_and_store_prices(db, game)
    refresh_catalog_seo_states(db)
    db.commit()
    db.refresh(game)
    return game


@router.get("/api/games/{slug}/trailer", response_model=TrailerResponse)
@limiter.limit("20/minute")
async def get_trailer(
    request: Request,
    slug: SlugPath,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    game = _get_game_or_404(db, slug)
    video_id = await cached_trailer_video_id(game.slug, game.title)
    return {
        "video_id": video_id,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


_facets_cache: FacetsResponse | None = None
_facets_cache_time: float = 0.0
_FACETS_TTL = 300.0  # 5 minutes
# Studio dropdown stays usable — the long tail of one-game developers is not offered.
_FACET_DEVELOPER_LIMIT = 40


@router.get("/api/facets", response_model=FacetsResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def get_facets(
    request: Request,
    db: Session = Depends(get_db),
) -> FacetsResponse:
    global _facets_cache, _facets_cache_time
    now = datetime.datetime.now().timestamp()
    if _facets_cache is not None and (now - _facets_cache_time) < _FACETS_TTL:
        return _facets_cache

    current_year = datetime.date.today().year
    # Expand JSON arrays at SQL level without loading ORM objects.
    # TRIM collapses variants like " MMORPG" / "MMORPG" into one facet entry.
    genres = list(db.scalars(json_array_values_statement(Game.genres)).all())

    years = list(db.scalars(
        select(Game.release_year)
        .where(Game.content_type == "game", Game.release_year <= current_year)
        .distinct()
        .order_by(Game.release_year.desc())
    ).all())

    raw_platforms = set(db.scalars(json_array_values_statement(Game.platforms)).all())

    developers = list(db.scalars(
        select(Game.developer)
        .where(Game.content_type == "game", Game.developer.is_not(None), Game.developer != "")
        .group_by(Game.developer)
        .order_by(func.count(Game.id).desc(), Game.developer.asc())
        .limit(_FACET_DEVELOPER_LIMIT)
    ).all())

    result = FacetsResponse(
        genres=genres,
        years=years,
        platforms=sorted(build_platform_filters(raw_platforms)),
        developers=developers,
    )
    _facets_cache = result
    _facets_cache_time = now
    return result
