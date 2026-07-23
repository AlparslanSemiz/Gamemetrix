"""Match a game to its identifiers across external sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...services.external_id_matching import match_external_ids
from ._common import get_game_or_404

router = APIRouter()


@router.post("/match/external-ids")
async def match_game_external_ids(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    db: Session = Depends(get_db),
) -> dict:
    """Look up a game across all configured sources and upsert ExternalId rows."""
    game = get_game_or_404(db, game_id)
    matched = await match_external_ids(db, game)
    return {"game_id": game_id, "title": game.title, "matched": matched}
