"""Helpers shared across the admin sub-routers."""

from __future__ import annotations

from fastapi import HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Game


def game_id_path() -> Path:
    return Path(..., ge=1)


def get_game_or_404(db: Session, game_id: int) -> Game:
    game = db.scalar(select(Game).where(Game.id == game_id))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
