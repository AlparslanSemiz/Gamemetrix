from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Game

_SEED_DATA_PATH = Path(__file__).with_name("data") / "seed_games.json"


def _load_seed_games() -> list[dict[str, Any]]:
    with _SEED_DATA_PATH.open(encoding="utf-8") as fh:
        games = json.load(fh)
    for game in games:
        game["release_date"] = date.fromisoformat(game["release_date"])
    return games


def seed_games(db: Session) -> bool:
    """Bootstrap an empty database from the dev fixture.

    Runtime data belongs to the database and external imports. The fixture is only
    used for first-run local development, so restarts do not overwrite DB state.
    Returns True when rows were inserted.
    """
    existing_count = db.scalar(select(func.count(Game.id))) or 0
    if existing_count > 0:
        return False

    db.add_all(Game(**game_data) for game_data in _load_seed_games())
    db.commit()
    return True
