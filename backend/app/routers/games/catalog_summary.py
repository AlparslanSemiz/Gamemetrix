"""Lightweight catalog endpoints used by cards, collections and alerts."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import get_db
from ...models import Game
from ...rate_limit import limiter
from ...schemas import (
    CatalogGameListResponse,
    CatalogGameRead,
    GameSlugBatchRequest,
    GameSort,
    SortDirection,
)
from ...services.catalog_projection import catalog_load_options
from ...services.game_query import (
    CatalogFilters,
    apply_advanced_filters,
    build_catalog_count_query,
    build_catalog_query,
)
from ._common import ContentTypeFilter, DealFilter, PlayerModeFilter

router = APIRouter()


@router.get("/api/catalog/games", response_model=CatalogGameListResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def list_catalog_games(
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
    limit: int = Query(default=24, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> CatalogGameListResponse:
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
    page_query = apply_advanced_filters(
        build_catalog_query(
            content_type,
            q,
            year_min,
            year_max,
            min_score,
            max_score,
            deal,
            sort,
            direction,
        ),
        advanced,
    )
    count_query = apply_advanced_filters(
        build_catalog_count_query(
            content_type,
            q,
            year_min,
            year_max,
            min_score,
            max_score,
            deal,
        ),
        advanced,
    )
    games = list(
        db.scalars(
            page_query
            .options(*catalog_load_options(include_prices=deal != "all"))
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return CatalogGameListResponse(
        games=[CatalogGameRead.model_validate(game) for game in games],
        total=db.scalar(count_query) or 0,
    )


@router.post("/api/catalog/games/batch", response_model=CatalogGameListResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
def catalog_games_by_slug(
    request: Request,
    payload: GameSlugBatchRequest,
    include_prices: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> CatalogGameListResponse:
    rows = list(
        db.scalars(
            select(Game)
            .where(Game.slug.in_(payload.slugs))
            .options(*catalog_load_options(include_prices=include_prices))
        ).all()
    )
    by_slug = {game.slug: game for game in rows}
    games = [by_slug[slug] for slug in payload.slugs if slug in by_slug]
    return CatalogGameListResponse(
        games=[CatalogGameRead.model_validate(game) for game in games],
        total=len(games),
    )
