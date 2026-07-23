"""Paginated catalog listing and the filter-option facets."""

import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload, selectinload

from ...config import get_settings
from ...database import get_db
from ...models import Game
from ...rate_limit import limiter
from ...schemas import FacetsResponse, GameListResponse, GameSort, SortDirection
from ...services.game_query import (
    CatalogFilters,
    apply_advanced_filters,
    build_catalog_count_query,
    build_catalog_query,
    build_platform_filters,
    json_array_values_statement,
)
from ._common import ContentTypeFilter, DealFilter, PlayerModeFilter

router = APIRouter()

_FACETS_TTL = 300.0  # 5 minutes
# Studio dropdown stays usable — the long tail of one-game developers is not offered.
_FACET_DEVELOPER_LIMIT = 40

_facets_cache: FacetsResponse | None = None
_facets_cache_time: float = 0.0


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
        build_catalog_query(
            content_type, q, year_min, year_max, min_score, max_score, deal, sort, direction
        ),
        advanced,
    )
    count_q = apply_advanced_filters(
        build_catalog_count_query(content_type, q, year_min, year_max, min_score, max_score, deal),
        advanced,
    )
    price_options = (
        selectinload(Game.price_snapshots) if deal != "all" else noload(Game.price_snapshots)
    )

    total = db.scalar(count_q) or 0
    page_q = base_q.options(price_options).offset(offset).limit(limit)
    return GameListResponse(games=list(db.scalars(page_q).all()), total=total)


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

    result = FacetsResponse(
        # Expand JSON arrays at SQL level without loading ORM objects.
        # TRIM collapses variants like " MMORPG" / "MMORPG" into one facet entry.
        genres=list(db.scalars(json_array_values_statement(Game.genres)).all()),
        years=_release_years(db),
        platforms=sorted(
            build_platform_filters(set(db.scalars(json_array_values_statement(Game.platforms)).all()))
        ),
        developers=_top_developers(db),
    )
    _facets_cache = result
    _facets_cache_time = now
    return result


def _release_years(db: Session) -> list[int]:
    current_year = datetime.date.today().year
    return list(db.scalars(
        select(Game.release_year)
        .where(Game.content_type == "game", Game.release_year <= current_year)
        .distinct()
        .order_by(Game.release_year.desc())
    ).all())


def _top_developers(db: Session) -> list[str]:
    return list(db.scalars(
        select(Game.developer)
        .where(Game.content_type == "game", Game.developer.is_not(None), Game.developer != "")
        .group_by(Game.developer)
        .order_by(func.count(Game.id).desc(), Game.developer.asc())
        .limit(_FACET_DEVELOPER_LIMIT)
    ).all())
