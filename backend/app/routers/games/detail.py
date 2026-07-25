"""Single-game detail, related games and trailer lookup."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import SessionLocal, get_db
from ...models import Game
from ...rate_limit import limiter
from ...schemas import GameListResponse, GameRead, SeoGenreRef, SeriesResponse, TrailerResponse
from ...security import AuthenticatedUser, optional_admin_user
from ...services.metadata_backfill import (
    game_needs_metadata_backfill,
    refresh_game_metadata,
    system_requirements_need_repair,
)
from ...services.seo import MIN_GENRE_LANDING_GAMES, breadcrumb_genre
from ...services.similarity import (
    find_series_games,
    find_similar_games,
    rerank_with_ai,
    series_key_for_title,
)
from ...services.trailer_cache import cached_trailer_video_id
from ._common import SlugPath, get_game_or_404, steam_app_id_for

router = APIRouter()
log = logging.getLogger(__name__)

TRAILER_RATE_LIMIT = "20/minute"
_YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v="


@router.get("/api/games/{slug}", response_model=GameRead)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def get_game(
    request: Request,
    slug: SlugPath,
    background_tasks: BackgroundTasks,
    refresh_metadata: bool = Query(default=False, alias="refresh"),
    db: Session = Depends(get_db),
    admin: AuthenticatedUser | None = Depends(optional_admin_user),
) -> GameRead:
    game = get_game_or_404(db, slug)
    if refresh_metadata and admin is None:
        raise HTTPException(status_code=403, detail="Admin role required to refresh metadata.")
    if refresh_metadata and _needs_detail_refresh(game):
        background_tasks.add_task(_refresh_game_detail_metadata, game.slug)
    response = GameRead.model_validate(game)
    crumb = breadcrumb_genre(db, game, MIN_GENRE_LANDING_GAMES)
    response.seo_genre = SeoGenreRef(slug=crumb[0], name=crumb[1]) if crumb else None
    return response


def _needs_detail_refresh(game: Game) -> bool:
    has_steam_art = steam_app_id_for(game) is not None
    return game_needs_metadata_backfill(game) or (
        has_steam_art and system_requirements_need_repair(game.system_requirements)
    )


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


@router.get("/api/games/{slug}/similar", response_model=GameListResponse)
@limiter.limit(get_settings().PUBLIC_READ_RATE_LIMIT)
async def get_similar_games(
    request: Request,
    slug: SlugPath,
    limit: int = Query(default=10, ge=1, le=24),
    db: Session = Depends(get_db),
) -> GameListResponse:
    game = get_game_or_404(db, slug)
    cfg = get_settings()
    pool_size = max(limit, cfg.SIMILARITY_AI_POOL) if cfg.SIMILARITY_USE_AI else limit
    candidates = find_similar_games(db, game, display_limit=pool_size)
    similar = await rerank_with_ai(game, candidates, limit)
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
    game = get_game_or_404(db, slug)
    series = find_series_games(db, game, limit=limit)
    return SeriesResponse(
        series_key=series_key_for_title(game.title),
        games=series,
        total=len(series),
    )


@router.get("/api/games/{slug}/trailer", response_model=TrailerResponse)
@limiter.limit(TRAILER_RATE_LIMIT)
async def get_trailer(
    request: Request,
    slug: SlugPath,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    game = get_game_or_404(db, slug)
    video_id = await cached_trailer_video_id(game.slug, game.title)
    return {
        "video_id": video_id,
        "watch_url": f"{_YOUTUBE_WATCH_URL}{video_id}" if video_id else None,
    }
