"""
Rating and metadata maintenance endpoints.

Routes:
  GET  /api/integrations/status          — provider health overview
  GET  /api/score-weights                — current source weights
  PUT  /api/score-weights                — update source weights at runtime
  POST /api/score-weights/recalculate    — recompute all game scores
  POST /api/ratings/enrich               — trigger a rating refresh batch
  POST /api/metadata/fix-years           — fix games with release_year=1970
  POST /api/metadata/backfill             — fill missing cover/media/source metadata
  POST /api/metadata/enrich-summaries    — enrich weak/placeholder summaries
"""

import math

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Game
from ..schemas import (
    MetadataFixResponse,
    ProviderStatus,
    RatingsEnrichResponse,
    RecalculateResponse,
    ScoreWeightsResponse,
    ScoreWeightsUpdate,
)
from ..integrations.provider_status import get_provider_statuses
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.source_registry import RATING_SOURCES
from ..integrations.sync import SOURCE_WEIGHTS, calculate_metrix_score, compute_rank_fields, refresh_game_sources
from ..integrations.rawg_score import get_rawg_game_metadata
from ..services.background import fix_year_batch, rating_refresh_candidates, refresh_all_games
from ..services.metadata_backfill import metadata_backfill_batch
from ..services.metadata import summary_needs_enrichment
from ..services.rawg_import import apply_rawg_metadata
from ..services.summarizer import shorten_summary_batch
from ..security import require_admin_user
from ..heavy_jobs import require_not_peak_hours

router = APIRouter(tags=["ratings"])


@router.get("/api/integrations/status", response_model=list[ProviderStatus])
def integration_status() -> list[dict[str, str]]:
    return get_provider_statuses()


def _rating_source_weights() -> dict[str, dict[str, float]]:
    """Only the rating sources are tunable; support sources are pinned at 0.0."""
    return {
        "weights": {
            source: value for source, value in SOURCE_WEIGHTS.items() if source in RATING_SOURCES
        }
    }


@router.get("/api/score-weights", response_model=ScoreWeightsResponse)
def get_score_weights() -> dict[str, dict[str, float]]:
    return _rating_source_weights()


@router.put("/api/score-weights", response_model=ScoreWeightsResponse)
def update_score_weights(
    payload: ScoreWeightsUpdate,
    _admin=Depends(require_admin_user),
) -> dict[str, dict[str, float]]:
    for source, value in payload.weights.items():
        if source not in RATING_SOURCES:
            raise HTTPException(status_code=422, detail=f"Unknown score source: {source}")
        if not math.isfinite(value):
            raise HTTPException(status_code=422, detail=f"Invalid score weight for {source}")
        SOURCE_WEIGHTS[source] = max(0.0, min(float(value), 1.0))
    return _rating_source_weights()


@router.post("/api/score-weights/recalculate", response_model=RecalculateResponse)
def recalculate_scores(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> dict[str, int]:
    games = db.query(Game).all()
    for game in games:
        game.metrix_score = calculate_metrix_score(game.source_scores)
        game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    from ..services.seo import refresh_catalog_seo_states
    refresh_catalog_seo_states(db)
    db.commit()
    return {"recalculated": len(games)}


@router.post("/api/ratings/enrich", response_model=RatingsEnrichResponse)
async def enrich_ratings(
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> dict[str, int]:
    enriched = 0
    for game in rating_refresh_candidates(db):
        await refresh_game_sources(db, game)
        enriched += 1
        if enriched >= limit:
            break
    return {"enriched": enriched, "skipped": 0}


@router.get("/api/rate-limits")
def get_rate_limit_status(
    _admin=Depends(require_admin_user),
) -> dict[str, dict[str, object]]:
    """Remaining persistent daily, monthly, and short-window provider budgets.

    Mirrors RateLimiter.status(). Without a response_model FastAPI validates against
    this annotation, so narrowing it to int rejects every response: a source entry
    also carries the nested per-window breakdown, reserve_percent and metered.
    """
    return get_rate_limiter().status()


@router.post("/api/ratings/refresh-all")
async def refresh_all_scores(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    concurrency: int = Query(default=3, ge=1, le=8),
    _admin=Depends(require_admin_user),
    _peak=Depends(require_not_peak_hours),
) -> dict[str, str]:
    """
    Trigger a full refresh of every game's scores in the background.
    Returns immediately; refresh runs concurrently with the given semaphore size.

    The actual work (services.background.refresh_all_games) acquires the same
    HEAVY_JOB_LOCK that /api/import/* holds for its whole request — so this
    can be triggered while an import is running and will simply report
    "already_running" rather than doubling up the load. See app/heavy_jobs.py.
    """
    background_tasks.add_task(refresh_all_games, concurrency=concurrency, force=force)
    return {"status": "started", "message": f"Refreshing all games (concurrency={concurrency}, force={force})"}


@router.post("/api/metadata/fix-years", response_model=MetadataFixResponse)
async def fix_missing_years(
    limit: int = Query(default=100, ge=1, le=500),
    _admin=Depends(require_admin_user),
) -> dict[str, int]:
    return await fix_year_batch(limit)


@router.post("/api/metadata/backfill")
async def backfill_missing_metadata(
    limit: int = Query(default=24, ge=1, le=100),
    inter_game_delay: float = Query(default=0.5, ge=0, le=5),
    _admin=Depends(require_admin_user),
) -> dict[str, object]:
    return await metadata_backfill_batch(limit=limit, inter_game_delay=inter_game_delay)


@router.post("/api/metadata/shorten-summaries", response_model=MetadataFixResponse)
async def shorten_summaries(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> dict[str, int]:
    result = await shorten_summary_batch(db, limit)
    return {"fixed": result["shortened"], "skipped": result["skipped"]}


@router.post("/api/metadata/enrich-summaries", response_model=MetadataFixResponse)
async def enrich_summaries(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
) -> dict[str, int]:
    fixed = 0
    skipped = 0
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .order_by(desc(Game.metrix_score))
        ).all()
    )
    for game in games:
        if fixed >= limit:
            break
        if not summary_needs_enrichment(game):
            skipped += 1
            continue
        if not await get_rate_limiter().acquire("RAWG"):
            break
        raw_game = await get_rawg_game_metadata(game.title)
        if not raw_game or not apply_rawg_metadata(game, raw_game):
            skipped += 1
            continue
        db.add(game)
        db.commit()
        db.refresh(game)
        fixed += 1
    return {"fixed": fixed, "skipped": skipped}
