"""Shared path types, lookups and filter literals for the game endpoints."""

from typing import Annotated, Literal

from fastapi import HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...integrations.steam import resolve_steam_app_id
from ...models import Game, SlugRedirect

ContentTypeFilter = Literal["all", "game", "dlc", "demo", "mod", "software", "soundtrack", "utility"]
DealFilter = Literal["all", "best", "free"]
PlayerModeFilter = Literal["singleplayer", "multiplayer", "coop"]

SlugPath = Annotated[str, Path(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


def get_game_or_404(db: Session, slug: str, *, redirect: bool = False) -> Game:
    """Load a game by slug, following `slug_redirects` left behind by merged duplicates.

    With `redirect=True` (the detail endpoint) a moved slug answers 301 with the
    canonical API location; elsewhere the merged game is simply served.
    """
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is not None:
        return game
    moved = db.scalar(
        select(Game).join(SlugRedirect, SlugRedirect.game_id == Game.id).where(SlugRedirect.old_slug == slug)
    )
    if moved is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if redirect:
        raise HTTPException(
            status_code=301,
            detail="Game moved",
            headers={"Location": f"/api/games/{moved.slug}", "X-Canonical-Slug": moved.slug},
        )
    return moved


def steam_app_id_for(game: Game) -> int | None:
    """The one Steam app id for a game: stored id first, then Steam art URLs."""
    return resolve_steam_app_id(game)


def require_steam_app_id(game: Game) -> int:
    app_id = steam_app_id_for(game)
    if app_id is None:
        raise HTTPException(status_code=422, detail="No Steam App ID found for this game.")
    return app_id
