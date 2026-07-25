"""
Game import endpoints — bulk data ingestion from free external sources.

Routes:
  POST /api/import/rawg          — RAWG catalog import
  POST /api/import/rawg/nintendo — RAWG Nintendo-family catalog import
  POST /api/import/igdb/nintendo — IGDB Nintendo-family catalog import
  POST /api/import/igdb/full     — resumable complete IGDB main-game catalog
  POST /api/import/steam/catalog — resumable official Steam game catalog
  POST /api/import/free-to-game  — FreeToGame catalog import
  POST /api/import/cheapshark    — CheapShark deals import
  POST /api/import/steamspy      — SteamSpy top-games import
  POST /api/import/hltb          — HowLongToBeat playtime/covers backfill
  POST /api/import/free-sources  — all three free sources in one call
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ImportResponse, MultiImportResponse
from ..integrations.cheapshark import import_cheapshark_deals
from ..integrations.free_to_game import import_free_to_game_games
from ..integrations.igdb_import import import_igdb_full_catalog, import_igdb_nintendo_games
from ..integrations.hltb import backfill_hltb_playtimes
from ..integrations.rawg import import_catalog_to_size, import_rawg_games, import_rawg_nintendo_games
from ..integrations.steamspy import import_steamspy_games
from ..integrations.steam_catalog import import_steam_official_catalog
from ..security import require_admin_user
from ..heavy_jobs import require_heavy_job_slot, require_not_peak_hours

router = APIRouter(
    prefix="/api/import",
    tags=["imports"],
    dependencies=[
        Depends(require_admin_user),
        # Fails fast (429) if we're in a configured peak-hour window, or if
        # another import / ratings refresh-all is already running — these
        # imports run inline (not as background tasks) and each one fans out
        # hundreds-to-thousands of outbound HTTP calls, so on a 1GB host only
        # one heavy job may run at a time. See app/heavy_jobs.py.
        Depends(require_not_peak_hours),
        Depends(require_heavy_job_slot),
    ],
)


@router.post("/rawg", response_model=ImportResponse)
async def import_from_rawg(
    target: int = Query(default=3000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return await import_rawg_games(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rawg/nintendo", response_model=ImportResponse)
async def import_nintendo_from_rawg(
    target: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return await import_rawg_nintendo_games(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/igdb/nintendo", response_model=ImportResponse)
async def import_nintendo_from_igdb(
    target: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return await import_igdb_nintendo_games(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/igdb/full")
async def import_full_catalog_from_igdb(
    target: int = Query(default=5000, ge=1, le=50000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        return await import_igdb_full_catalog(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/steam/catalog")
async def import_official_catalog_from_steam(
    target: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        return await import_steam_official_catalog(db, target=target)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/catalog")
async def import_catalog(
    target_total: int = Query(default=50000, ge=1, le=250000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        return await import_catalog_to_size(db, target_total=target_total)
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


@router.post("/hltb")
async def import_from_hltb(
    target: int = Query(default=500, ge=1, le=5000),
    refresh_existing: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await backfill_hltb_playtimes(
        db,
        target=target,
        refresh_existing=refresh_existing,
    )


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
