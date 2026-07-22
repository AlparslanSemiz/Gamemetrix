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

import asyncio
import datetime
import logging
import time
from collections import OrderedDict
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request
from sqlalchemy import BigInteger, Float, Select, and_, asc, case, cast, desc, exists, func, or_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, noload, selectinload

from ..config import get_settings
from ..database import SessionLocal, get_db
from ..models import Game, PriceSnapshot, infer_content_type
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
from ..integrations.youtube import find_trailer_video_id
from ..services.game_filter import (
    LIKE_ESCAPE_CHAR,
    escape_like,
)
from ..integrations.source_registry import CRITIC_SOURCES, PC_PLATFORM_KEYS, PRIMARY_SOURCES
from ..services.deduplication import find_existing_duplicate, merge_game_data
from ..services.game_similarity import find_series_games, find_similar_games, series_key_for_title
from ..services.metadata_backfill import game_needs_metadata_backfill, refresh_game_metadata
from ..services.price_backfill import fetch_and_store_prices
from ..services.rawg_import import apply_rawg_to_game, game_from_rawg_search
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


_PLAYER_MODE_GENRE_ALIASES: dict[str, frozenset[str]] = {
    "multiplayer": frozenset({"massively multiplayer", "mmo", "mmorpg", "mmoarpg", "multiplayer", "pvp", "online co-op"}),
    "coop": frozenset({"co-op", "coop", "online co-op", "local co-op"}),
    "singleplayer": frozenset({"single player", "singleplayer"}),
}


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
    base_q = _build_db_query(content_type, q, year_min, year_max, min_score, max_score, deal, sort, direction)
    base_q = _apply_advanced_db_filters(
        base_q, genre, developer, publisher, platform, min_ratings, max_ratings,
        has_award, min_live_sources, require_critic, player_mode,
        playtime_min_hours, playtime_max_hours,
    )
    price_options = selectinload(Game.price_snapshots) if deal != "all" else noload(Game.price_snapshots)

    count_q = _build_count_query(content_type, q, year_min, year_max, min_score, max_score, deal)
    count_q = _apply_advanced_db_filters(
        count_q, genre, developer, publisher, platform, min_ratings, max_ratings,
        has_award, min_live_sources, require_critic, player_mode,
        playtime_min_hours, playtime_max_hours,
    )
    total = db.scalar(count_q) or 0
    page_q = base_q.options(price_options).offset(offset).limit(limit)
    games = list(db.scalars(page_q).all())
    return GameListResponse(games=games, total=total)


def _build_count_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    deal: str,
) -> Select[tuple[int]]:
    """Direct COUNT — no subquery, uses indexes on content_type/rank_score."""
    query = select(func.count(Game.id))
    if content_type != "all":
        query = query.where(Game.content_type == content_type)
    if q:
        query = query.where(Game.title.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE_CHAR))
    if year_min is not None:
        query = query.where(Game.release_year >= year_min)
    if year_max is not None:
        query = query.where(Game.release_year <= year_max)
    if min_score is not None:
        query = query.where(Game.metrix_score >= min_score)
    if max_score is not None:
        query = query.where(Game.metrix_score <= max_score)
    query = _apply_deal_filter(query, deal)
    return query


def _build_db_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    deal: str,
    sort: str,
    direction: str,
) -> Select[tuple[Game]]:
    query = select(Game)
    if content_type != "all":
        query = query.where(Game.content_type == content_type)
    if q:
        query = query.where(Game.title.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE_CHAR))
    if year_min is not None:
        query = query.where(Game.release_year >= year_min)
    if year_max is not None:
        query = query.where(Game.release_year <= year_max)
    if min_score is not None:
        query = query.where(Game.metrix_score >= min_score)
    if max_score is not None:
        query = query.where(Game.metrix_score <= max_score)
    query = _apply_deal_filter(query, deal)
    return _apply_db_sort(query, sort, direction)


def _apply_deal_filter(query: Select, deal: str) -> Select:
    fresh_before = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=24)
    if deal == "free":
        free_price = exists(
            select(PriceSnapshot.id).where(
                PriceSnapshot.game_id == Game.id,
                PriceSnapshot.is_free.is_(True),
                PriceSnapshot.fetched_at >= fresh_before,
            )
        )
        return query.where(free_price)
    if deal == "best":
        discounted_price = exists(
            select(PriceSnapshot.id).where(
                PriceSnapshot.game_id == Game.id,
                PriceSnapshot.fetched_at >= fresh_before,
                or_(
                    PriceSnapshot.is_free.is_(True),
                    PriceSnapshot.discount_percent >= 50,
                    (
                        PriceSnapshot.sale_price.is_not(None)
                        & PriceSnapshot.list_price.is_not(None)
                        & (PriceSnapshot.sale_price < PriceSnapshot.list_price)
                    ),
                ),
            )
        )
        return query.where(discounted_price)
    return query


def _apply_db_sort(query: Select[tuple[Game]], sort: str, direction: str) -> Select[tuple[Game]]:
    score_tiebreakers = (desc(Game.rank_score), desc(Game.metrix_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))
    if sort == "title":
        col = desc(Game.title) if direction == "desc" else asc(Game.title)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.id))
    if sort == "release_year":
        col = desc(Game.release_year) if direction == "desc" else asc(Game.release_year)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    if sort == "critic_score":
        col = desc(Game.critic_score) if direction == "desc" else asc(Game.critic_score)
        return query.order_by(col, *score_tiebreakers)
    if sort == "user_score":
        col = desc(Game.user_score) if direction == "desc" else asc(Game.user_score)
        return query.order_by(col, *score_tiebreakers)
    if sort == "metrix_score":
        col = desc(Game.metrix_score) if direction == "desc" else asc(Game.metrix_score)
        return query.order_by(col, desc(Game.rank_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))
    source_map = {
        "metacritic_score": "Metacritic",
        "opencritic_score": "OpenCritic",
        "steam_score": "Steam",
    }
    if sort in source_map:
        source_score = _source_score_expression(source_map[sort])
        col = desc(source_score) if direction == "desc" else asc(source_score)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    if sort == "review_count":
        reviews = _review_count_expression(require_live_score=False)
        col = desc(reviews) if direction == "desc" else asc(reviews)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    # Default (rank_score) — reliability-weighted ranking
    col = desc(Game.rank_score) if direction == "desc" else asc(Game.rank_score)
    return query.order_by(col, desc(Game.metrix_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))


def _json_array_match(column, values: set[str] | frozenset[str], *, substring: bool = False):
    rows = func.jsonb_array_elements_text(cast(column, JSONB)).table_valued("value")
    stored = func.lower(func.trim(rows.c.value))
    if substring:
        condition = or_(*(func.strpos(stored, value) > 0 for value in values))
    else:
        condition = stored.in_(values)
    return exists(select(1).select_from(rows).where(condition)).correlate(Game)


def _source_score_parts():
    rows = func.jsonb_array_elements(cast(Game.source_scores, JSONB)).table_valued("value")
    item = cast(rows.c.value, JSONB)
    numeric_score = case(
        (func.jsonb_typeof(item["score"]) == "number", cast(item["score"].astext, Float)),
        else_=0.0,
    )
    valid = and_(
        item["status"].astext == "live",
        numeric_score > 0,
        numeric_score <= 100,
    )
    return rows, item, numeric_score, valid


def _source_score_expression(source: str):
    rows, item, numeric_score, valid = _source_score_parts()
    return (
        select(func.coalesce(func.max(case((and_(valid, item["source"].astext == source), numeric_score), else_=0.0)), 0.0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _review_count_expression(*, require_live_score: bool):
    rows, item, _numeric_score, valid = _source_score_parts()
    numeric_reviews = case(
        (func.jsonb_typeof(item["review_count"]) == "number", cast(item["review_count"].astext, BigInteger)),
        else_=0,
    )
    safe_reviews = and_(numeric_reviews >= 0, numeric_reviews <= 2_000_000_000)
    condition = and_(valid, safe_reviews) if require_live_score else safe_reviews
    return (
        select(func.coalesce(func.sum(case((condition, numeric_reviews), else_=0)), 0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _live_primary_source_count_expression():
    rows, item, _numeric_score, valid = _source_score_parts()
    pc_platform = _json_array_match(Game.platforms, PC_PLATFORM_KEYS)
    applicable_source = or_(
        item["source"].astext.in_(PRIMARY_SOURCES - {"Steam"}),
        and_(item["source"].astext == "Steam", pc_platform),
    )
    return (
        select(func.coalesce(func.sum(case((and_(valid, applicable_source), 1), else_=0)), 0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _has_live_critic_expression():
    rows, item, _numeric_score, valid = _source_score_parts()
    return exists(
        select(1).select_from(rows).where(and_(valid, item["source"].astext.in_(CRITIC_SOURCES)))
    ).correlate(Game)


def _apply_advanced_db_filters(
    query: Select,
    genre: str | None,
    developer: str | None,
    publisher: str | None,
    platform: str | None,
    min_ratings: int | None,
    max_ratings: int | None,
    has_award: bool,
    min_live_sources: int | None,
    require_critic: bool,
    player_mode: str | None = None,
    playtime_min_hours: float | None = None,
    playtime_max_hours: float | None = None,
) -> Select:
    if genre:
        query = query.where(_json_array_match(Game.genres, {genre.strip().lower()}))
    if developer:
        query = query.where(func.lower(Game.developer) == developer.lower())
    if publisher:
        query = query.where(func.lower(Game.publisher) == publisher.lower())
    if platform:
        terms = {platform.lower()}
        if platform.lower() == "steam":
            terms.add("pc")
        query = query.where(_json_array_match(Game.platforms, terms, substring=True))
    if player_mode:
        query = query.where(or_(
            _json_array_match(Game.game_modes, {player_mode}),
            _json_array_match(Game.genres, _PLAYER_MODE_GENRE_ALIASES[player_mode]),
        ))
    if playtime_min_hours is not None:
        query = query.where(Game.playtime_minutes > 0, Game.playtime_minutes >= playtime_min_hours * 60)
    if playtime_max_hours is not None:
        query = query.where(Game.playtime_minutes > 0, Game.playtime_minutes <= playtime_max_hours * 60)
    if min_ratings is not None:
        query = query.where(_review_count_expression(require_live_score=True) >= min_ratings)
    if max_ratings is not None:
        query = query.where(_review_count_expression(require_live_score=True) <= max_ratings)
    if has_award:
        query = query.where(or_(Game.goty_year.is_not(None), Game.award_count > 0))
    if min_live_sources is not None:
        query = query.where(_live_primary_source_count_expression() >= min_live_sources)
    if require_critic:
        query = query.where(_has_live_critic_expression())
    return query


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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    refreshed = await refresh_game_sources(db, game)
    from ..services.seo import refresh_catalog_seo_states
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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    await fetch_and_store_prices(db, game)
    from ..services.seo import refresh_catalog_seo_states
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
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    video_id = await _cached_trailer_video_id(game.slug, game.title)
    return {
        "video_id": video_id,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


_TRAILER_CACHE_TTL = 6 * 60 * 60
_TRAILER_CACHE_MAX_SIZE = 1000
_trailer_cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
_trailer_inflight: dict[str, asyncio.Task[str | None]] = {}
_trailer_cache_lock = asyncio.Lock()
_trailer_lookup_slots = asyncio.Semaphore(4)


async def _cached_trailer_video_id(slug: str, title: str) -> str | None:
    now = time.monotonic()
    async with _trailer_cache_lock:
        cached = _trailer_cache.get(slug)
        if cached and now - cached[0] < _TRAILER_CACHE_TTL:
            _trailer_cache.move_to_end(slug)
            return cached[1]
        task = _trailer_inflight.get(slug)
        if task is None:
            task = asyncio.create_task(_lookup_and_cache_trailer(slug, title))
            _trailer_inflight[slug] = task
    return await asyncio.shield(task)


async def _lookup_and_cache_trailer(slug: str, title: str) -> str | None:
    try:
        async with _trailer_lookup_slots:
            video_id = await find_trailer_video_id(title)
        async with _trailer_cache_lock:
            _trailer_cache[slug] = (time.monotonic(), video_id)
            _trailer_cache.move_to_end(slug)
            while len(_trailer_cache) > _TRAILER_CACHE_MAX_SIZE:
                _trailer_cache.popitem(last=False)
        return video_id
    finally:
        current = asyncio.current_task()
        async with _trailer_cache_lock:
            if _trailer_inflight.get(slug) is current:
                _trailer_inflight.pop(slug, None)


_facets_cache: FacetsResponse | None = None
_facets_cache_time: float = 0.0
_FACETS_TTL = 300.0  # 5 minutes
# Studio dropdown stays usable — the long tail of one-game developers is not offered.
_FACET_DEVELOPER_LIMIT = 40


def _json_array_values_statement(column):
    values = func.jsonb_array_elements_text(cast(column, JSONB)).table_valued("value").lateral()
    trimmed = func.trim(values.c.value).label("value")
    return (
        select(trimmed)
        .distinct()
        .select_from(Game)
        .join(values, true())
        .where(Game.content_type == "game", trimmed != "")
        .order_by(trimmed)
    )


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
    genres = list(db.scalars(_json_array_values_statement(Game.genres)).all())

    years = list(db.scalars(
        select(Game.release_year)
        .where(Game.content_type == "game", Game.release_year <= current_year)
        .distinct()
        .order_by(Game.release_year.desc())
    ).all())

    raw_platforms = set(db.scalars(_json_array_values_statement(Game.platforms)).all())

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
        platforms=sorted(_build_platform_filters(raw_platforms)),
        developers=developers,
    )
    _facets_cache = result
    _facets_cache_time = now
    return result


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
