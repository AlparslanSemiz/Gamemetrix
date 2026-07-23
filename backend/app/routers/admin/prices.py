"""On-demand single-game price imports from ITAD and CheapShark."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...integrations.itad_service import itad_service
from ...services.price_import import import_cheapshark_price, import_itad_price
from ._common import get_game_or_404

router = APIRouter(prefix="/import/prices")


@router.post("/itad")
async def import_prices_itad(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    country: str = Query(
        default="EU",
        min_length=2,
        max_length=3,
        pattern=r"^[A-Za-z]{2,3}$",
        description="Region code (EU, US, ...)",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch current ITAD prices for a game and store in price_snapshots."""
    game = get_game_or_404(db, game_id)
    if not itad_service.is_configured():
        raise HTTPException(status_code=503, detail="ITAD_API_KEY not configured")
    result = await import_itad_price(db, game, country)
    return {"game_id": game_id, **result}


@router.post("/cheapshark")
async def import_prices_cheapshark(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch cheapest CheapShark deal for a game and store in price_snapshots."""
    game = get_game_or_404(db, game_id)
    result = await import_cheapshark_price(db, game)
    return {"game_id": game_id, **result}
