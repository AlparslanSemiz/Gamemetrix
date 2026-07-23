"""Shared path types, lookups and filter literals for the game endpoints."""

from typing import Annotated, Literal

from fastapi import HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...integrations.steam import extract_steam_app_id
from ...models import Game

ContentTypeFilter = Literal["all", "game", "dlc", "demo", "mod", "software", "soundtrack", "utility"]
DealFilter = Literal["all", "best", "free"]
PlayerModeFilter = Literal["singleplayer", "multiplayer", "coop"]

SlugPath = Annotated[str, Path(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


def get_game_or_404(db: Session, slug: str) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


def steam_app_id_for(game: Game) -> int | None:
    """Recover a Steam app id, preferring CDN art URLs over the slug."""
    return extract_steam_app_id(game.cover_url, game.image_url, game.slug)


def require_steam_app_id(game: Game) -> int:
    app_id = steam_app_id_for(game)
    if app_id is None:
        raise HTTPException(status_code=422, detail="No Steam App ID found for this game.")
    return app_id
