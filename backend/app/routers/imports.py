"""
Game import endpoints — bulk data ingestion from free external sources.

Routes:
  POST /api/import/rawg          — RAWG catalog import
  POST /api/import/free-to-game  — FreeToGame catalog import
  POST /api/import/cheapshark    — CheapShark deals import
  POST /api/import/steamspy      — SteamSpy top-games import
  POST /api/import/free-sources  — all three free sources in one call
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ImportResponse, MultiImportResponse
from ..integrations.cheapshark import import_cheapshark_deals
from ..integrations.free_to_game import import_free_to_game_games
from ..integrations.rawg import import_rawg_games
from ..integrations.steamspy import import_steamspy_games

router = APIRouter(prefix="/api/import", tags=["imports"])


@router.post("/rawg", response_model=ImportResponse)
async def import_from_rawg(
    target: int = Query(default=3000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return await import_rawg_games(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/free-to-game", response_model=ImportResponse)
async def import_from_free_to_game(
    target: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_free_to_game_games(db, target=target)


@router.post("/cheapshark", response_model=ImportResponse)
async def import_from_cheapshark(
    target: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_cheapshark_deals(db, target=target)


@router.post("/steamspy", response_model=ImportResponse)
async def import_from_steamspy(
    target: int = Query(default=3000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_steamspy_games(db, target=target)


@router.post("/free-sources", response_model=MultiImportResponse)
async def import_from_free_sources(
    free_to_game_target: int = Query(default=500, ge=1, le=1000),
    cheapshark_target: int = Query(default=500, ge=1, le=2000),
    steamspy_target: int = Query(default=3000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    results = {
        "FreeToGame": await import_free_to_game_games(db, target=free_to_game_target),
        "CheapShark": await import_cheapshark_deals(db, target=cheapshark_target),
        "SteamSpy": await import_steamspy_games(db, target=steamspy_target),
    }
    return {
        "imported": sum(int(r["imported"]) for r in results.values()),
        "skipped": sum(int(r["skipped"]) for r in results.values()),
        "sources": results,
    }
