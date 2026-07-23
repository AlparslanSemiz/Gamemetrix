"""Admin-triggered per-game refreshes: scores, screenshots, requirements, prices."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...integrations.steam import fetch_steam_screenshots, fetch_steam_system_requirements
from ...integrations.sync import refresh_game_sources
from ...models import Game
from ...schemas import GameRead
from ...security import require_admin_user
from ...services.price_backfill import fetch_and_store_prices
from ...services.seo import refresh_catalog_seo_states
from ._common import SlugPath, get_game_or_404, require_steam_app_id

router = APIRouter(prefix="/api/games/{slug}", dependencies=[Depends(require_admin_user)])


@router.post("/refresh-scores", response_model=GameRead)
async def refresh_game_scores(slug: SlugPath, db: Session = Depends(get_db)) -> Game:
    game = get_game_or_404(db, slug)
    refreshed = await refresh_game_sources(db, game)
    refresh_catalog_seo_states(db)
    db.commit()
    db.refresh(refreshed)
    return refreshed


@router.post("/fetch-screenshots", response_model=GameRead)
async def fetch_game_screenshots(slug: SlugPath, db: Session = Depends(get_db)) -> Game:
    game = get_game_or_404(db, slug)
    screenshots = await fetch_steam_screenshots(require_steam_app_id(game))
    if screenshots:
        game.screenshots = screenshots
        db.commit()
        db.refresh(game)
    return game


@router.post("/fetch-system-requirements", response_model=GameRead)
async def fetch_game_system_requirements(slug: SlugPath, db: Session = Depends(get_db)) -> Game:
    game = get_game_or_404(db, slug)
    requirements = await fetch_steam_system_requirements(require_steam_app_id(game))
    if requirements:
        game.system_requirements = requirements
        db.commit()
        db.refresh(game)
    return game


@router.post("/fetch-prices", response_model=GameRead)
async def fetch_game_prices(slug: SlugPath, db: Session = Depends(get_db)) -> Game:
    game = get_game_or_404(db, slug)
    await fetch_and_store_prices(db, game)
    refresh_catalog_seo_states(db)
    db.commit()
    db.refresh(game)
    return game
