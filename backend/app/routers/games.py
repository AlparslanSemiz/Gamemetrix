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
from sqlalchemy import Select, asc, desc, func, select, text
from sqlalchemy.orm import Session, noload

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
    fetch_steam_price,
    fetch_steam_screenshots,
    fetch_steam_system_requirements,
)
from ..integrations.sync import refresh_game_sources
from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.itad_service import itad_service
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
from ..services.deduplication import find_existing_duplicate, merge_game_data
from ..services.game_similarity import find_series_games, find_similar_games, series_key_for_title
from ..services.metadata_backfill import game_needs_metadata_backfill, refresh_game_metadata
from ..services.rawg_import import apply_rawg_to_game, game_from_rawg_search
from ..rate_limit import limiter
from ..security import require_admin_user

router = APIRouter(tags=["games"])
log = logging.getLogger(__name__)

_RAWG_SEARCH_TIMEOUT = 15
ContentTypeFilter = Literal["all", "game", "dlc", "demo", "mod", "software", "soundtrack", "utility"]
SlugPath = Annotated[str, Path(min_length=1, max_length=180)]


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
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"RAWG request failed: {exc}") from exc

    results = resp.json().get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="RAWG returned no matching game.")
    return results[0]


_IN_MEMORY_SORTS = {"metacritic_score", "opencritic_score", "steam_score", "review_count"}


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
    min_ratings: int | None = Query(default=None, ge=0),
    max_ratings: int | None = Query(default=None, ge=0),
    min_live_sources: int | None = Query(default=None, ge=0, le=10),
    require_critic: bool = False,
    has_award: bool = False,
    sort: GameSort = "rank_score",
    direction: SortDirection = "desc",
    limit: int = Query(default=120, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GameListResponse:
    base_q = _build_db_query(content_type, q, year_min, year_max, min_score, max_score, sort, direction)

    needs_memory_filter = any([genre, developer, publisher, platform, min_ratings, max_ratings, has_award, min_live_sources, require_critic])
    needs_memory_sort = sort in _IN_MEMORY_SORTS

    if not needs_memory_filter and not needs_memory_sort:
        # Fast path: DB handles sort + pagination. Only the requested page is loaded.
        # COUNT uses a direct WHERE-clause query (no subquery) for index efficiency.
        count_q = _build_count_query(content_type, q, year_min, year_max, min_score, max_score)
        total = db.scalar(count_q) or 0
        page_q = base_q.options(noload(Game.price_snapshots)).offset(offset).limit(limit)
        games = list(db.scalars(page_q).all())
        return GameListResponse(games=games, total=total)

    # Slow path: in-memory filters or JSON-based sort require loading all matches.
    all_q = base_q.options(noload(Game.price_snapshots))
    games = list(db.scalars(all_q).all())
    games = _apply_in_memory_filters(
        games, genre, developer, publisher, platform,
        min_ratings, max_ratings, has_award, min_live_sources, require_critic,
    )
    games = sort_in_memory(games, sort, direction)
    games = dedupe_near_duplicates(games)
    total = len(games)
    return GameListResponse(games=games[offset: offset + limit], total=total)


def _build_count_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
) -> Select[tuple[int]]:
    """Direct COUNT — no subquery, uses indexes on content_type/rank_score."""
    query = select(func.count(Game.id))
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
    return query


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
    # Default (rank_score) — reliability-weighted ranking
    col = desc(Game.rank_score) if direction == "desc" else asc(Game.rank_score)
    return query.order_by(col, desc(Game.metrix_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))


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
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def get_game(
    request: Request,
    slug: SlugPath,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)
    if game_needs_metadata_backfill(game) or (app_id and _system_requirements_need_repair(game.system_requirements)):
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
    slug: str,
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
    return await refresh_game_sources(db, game)


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

    await _fetch_and_store_prices(db, game)
    db.refresh(game)
    return game


async def _fetch_and_store_prices(db: Session, game: Game) -> int:
    now = datetime.datetime.now(datetime.UTC)
    fresh_cutoff = now - datetime.timedelta(hours=12)
    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)

    def _snapshot_is_recent(snapshot: PriceSnapshot) -> bool:
        fetched_at = snapshot.fetched_at
        if fetched_at is None:
            return False
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=datetime.UTC)
        return fetched_at >= fresh_cutoff

    def _snapshot_needs_repair(snapshot: PriceSnapshot) -> bool:
        raw = snapshot.raw_payload or {}
        if snapshot.store.startswith("Store "):
            return True
        if snapshot.source == "CheapShark" and app_id is not None:
            steam_app_id = raw.get("steam_app_id")
            if steam_app_id is None:
                return True
            return str(steam_app_id) != str(app_id)
        return False

    if (
        game.price_snapshots
        and (app_id is None or any(snapshot.source == "Steam" and snapshot.store == "Steam" for snapshot in game.price_snapshots))
        and not any(_snapshot_needs_repair(snapshot) for snapshot in game.price_snapshots)
        and any(_snapshot_is_recent(snapshot) for snapshot in game.price_snapshots)
    ):
        return 0

    rows: list[PriceSnapshot] = []

    if app_id is not None:
        steam_price = await fetch_steam_price(app_id)
        if steam_price:
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="Steam",
                external_price_id=str(app_id),
                store="Steam",
                platform="PC",
                region="US",
                currency=steam_price["currency"],
                list_price=steam_price["list_price"],
                sale_price=steam_price["sale_price"],
                discount_percent=steam_price["discount_percent"],
                is_free=steam_price["is_free"],
                url=steam_price["url"],
                raw_payload=steam_price["raw"],
                fetched_at=now,
                created_at=now,
            ))

    if itad_service.is_configured():
        price_data = await itad_service.fetch_price_data(game.title, steam_appid=app_id)
        if price_data:
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="ITAD",
                store=price_data.store or "Best tracked PC store",
                platform="PC",
                region="EU",
                currency=price_data.currency,
                list_price=price_data.list_price,
                sale_price=price_data.sale_price,
                discount_percent=price_data.discount_percent,
                historical_low=price_data.historical_low,
                historical_low_date=price_data.historical_low_date,
                is_free=price_data.is_free,
                is_subscription_included=price_data.is_subscription_included,
                subscription_service=price_data.subscription_service,
                itad_id=price_data.itad_id,
                fetched_at=now,
                created_at=now,
            ))

    cs_game_id = await cheapshark_service.lookup_game_id(game.title, steam_appid=app_id)
    deals = await cheapshark_service.get_game_deals(cs_game_id) if cs_game_id else []
    if not deals:
        deals = [
            deal for deal in await cheapshark_service.search_deals(game.title, limit=20)
            if _cheapshark_deal_matches_game(deal, game, app_id)
        ]
    if deals:
        seen_stores: set[str] = {row.store.lower() for row in rows}
        sorted_deals = sorted(deals, key=lambda d: float(d.get("salePrice", 9999)))
        for deal in sorted_deals:
            normalized = cheapshark_service.normalize_deal(deal)
            store = str(normalized.raw.get("store_name") or "PC store")
            store_key = store.lower()
            if store_key in seen_stores:
                continue
            seen_stores.add(store_key)
            deal_id = normalized.raw.get("cs_deal_id")
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="CheapShark",
                external_price_id=str(deal_id) if deal_id else None,
                store=store,
                platform="PC",
                region="US",
                currency=normalized.currency,
                list_price=normalized.list_price,
                sale_price=normalized.sale_price,
                discount_percent=int(normalized.raw.get("savings_pct", 0) or 0),
                url=f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else None,
                raw_payload=normalized.raw,
                fetched_at=now,
                created_at=now,
            ))
            if len(seen_stores) >= 12:
                break

    if rows:
        game.price_snapshots.clear()
        db.flush()
        db.add_all(rows)
        db.commit()
    return len(rows)


_PRICE_ADDON_TERMS = (
    "upgrade",
    "dlc",
    "soundtrack",
    "bundle",
    "pack",
    "season pass",
    "expansion",
)


def _price_title_key(value: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
    )


def _cheapshark_deal_matches_game(raw: dict, game: Game, app_id: int | None) -> bool:
    title = str(raw.get("title") or "")
    normalized_title = _price_title_key(title)
    expected = _price_title_key(game.title)
    if not normalized_title:
        return False
    if app_id is not None and raw.get("steamAppID") and str(raw.get("steamAppID")) != str(app_id):
        return False
    if any(term in normalized_title for term in _PRICE_ADDON_TERMS) and normalized_title != expected:
        return False
    return normalized_title == expected or expected in normalized_title or normalized_title in expected


@router.get("/api/games/{slug}/trailer", response_model=TrailerResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def get_trailer(
    request: Request,
    slug: SlugPath,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    video_id = await find_trailer_video_id(game.title)
    return {
        "video_id": video_id,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


_facets_cache: FacetsResponse | None = None
_facets_cache_time: float = 0.0
_FACETS_TTL = 300.0  # 5 minutes


def _json_array_values_sql(column: str, dialect_name: str) -> str:
    if dialect_name == "postgresql":
        return (
            f"SELECT DISTINCT TRIM(value) FROM games, "
            f"LATERAL jsonb_array_elements_text(games.{column}::jsonb) AS value"
            " WHERE games.content_type = 'game' AND TRIM(value) != ''"
        )
    return (
        f"SELECT DISTINCT TRIM(j.value) FROM games, json_each(games.{column}) j"
        " WHERE games.content_type = 'game' AND TRIM(j.value) != ''"
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
    dialect_name = db.bind.dialect.name if db.bind is not None else ""

    # Use json_each to expand JSON arrays at SQL level — no ORM object loading.
    # TRIM collapses variants like " MMORPG" / "MMORPG" into one facet entry.
    genre_rows = db.execute(
        text(f"{_json_array_values_sql('genres', dialect_name)} ORDER BY 1")
    ).fetchall()
    genres = [r[0] for r in genre_rows]

    year_rows = db.execute(
        text(
            "SELECT DISTINCT release_year FROM games"
            " WHERE content_type = 'game' AND release_year <= :yr ORDER BY release_year DESC"
        ),
        {"yr": current_year},
    ).fetchall()
    years = [r[0] for r in year_rows]

    platform_rows = db.execute(
        text(_json_array_values_sql("platforms", dialect_name))
    ).fetchall()
    raw_platforms = {r[0] for r in platform_rows}

    result = FacetsResponse(
        genres=genres,
        years=years,
        platforms=sorted(_build_platform_filters(raw_platforms)),
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
