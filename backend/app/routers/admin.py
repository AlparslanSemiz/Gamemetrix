"""
Admin / internal debug endpoints.

These endpoints are for developer/ops use only.
They are NOT part of the public product API; the admin UI may call them only after JWT login.
Every endpoint requires an admin JWT (router-level require_admin_user dependency);
production deployments should additionally restrict /admin/* at the network/proxy layer.

Endpoints:
  GET  /admin/api-health                     — masked health status for all sources
  GET  /admin/source-test/{source}?q=title   — live smoke test for one source
  GET  /admin/external-ids/{game_id}         — external IDs for a game
  GET  /admin/rating-snapshots/{game_id}     — rating history for a game
  GET  /admin/source-snapshots/{game_id}      — raw source fetch snapshots for a game
  GET  /admin/data-fill/status               — automated data fill status
  POST /admin/data-fill/run                  — queue automated data fill run
  GET  /admin/primary-scores/status          — 4 primary score coverage
  POST /admin/primary-scores/run             — complete OpenCritic/Metacritic/IGDB/Steam scores
  POST /admin/import/prices/itad             — fetch + store ITAD prices for a game
  POST /admin/import/prices/cheapshark       — fetch + store CheapShark prices for a game
  POST /admin/match/external-ids             — match game to external sources
"""

import asyncio
import dataclasses
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..heavy_jobs import HEAVY_JOB_LOCK
from ..models import ExternalId, Game, PriceSnapshot, RatingSnapshot, SourceSnapshot, VisitEvent, infer_content_type_with_parent
from ..services.data_fill import data_fill_status, execute_data_fill_run, queue_data_fill_run
from ..services.deduplication import consolidate_duplicate_games
from ..services.primary_score_backfill import primary_score_backfill_batch, primary_score_coverage_status
from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.igdb_service import igdb_service
from ..integrations.itad_service import itad_service
from ..integrations.opencritic_service import opencritic_service
from ..integrations.rawg_service import rawg_service
from ..integrations.steam_service import steam_service
from ..integrations.types import SourceHealth
from ..security import require_admin_user

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


class SourceTest(str, Enum):
    igdb = "igdb"
    rawg = "rawg"
    opencritic = "opencritic"
    steam = "steam"
    itad = "itad"
    cheapshark = "cheapshark"


# ── Health check ─────────────────────────────────────────────────────────────


@router.get("/api-health")
async def api_health() -> dict:
    """
    Returns masked health status for every configured API source.
    Keys, tokens, and secrets are NEVER included in the response.
    """
    cfg = get_settings()

    checks: list[asyncio.Task[SourceHealth]] = []
    labels: list[str] = []

    async def _safe(label: str, coro) -> SourceHealth:
        try:
            return await asyncio.wait_for(coro, timeout=15)
        except asyncio.TimeoutError:
            return SourceHealth(
                source=label,
                configured=True,
                working=False,
                status="failing",
                message="Health check timed out after 15s",
            )
        except Exception as exc:
            return SourceHealth(
                source=label,
                configured=True,
                working=False,
                status="failing",
                message=f"Unexpected error: {type(exc).__name__}",
            )

    results = await asyncio.gather(
        _safe("igdb", igdb_service.health_check()),
        _safe("rawg", rawg_service.health_check()),
        _safe("opencritic", opencritic_service.health_check()),
        _safe("steam", steam_service.health_check()),
        _safe("itad", itad_service.health_check()),
        _safe("cheapshark", cheapshark_service.health_check()),
    )

    return {
        h.source: {
            "configured": h.configured,
            "working": h.working,
            "status": h.status,
            **({"message": h.message} if h.message else {}),
            **({"latency_ms": h.latency_ms} if h.latency_ms is not None else {}),
        }
        for h in results
    }


# ── Dashboard / traffic analytics ────────────────────────────────────────────


@router.get("/dashboard")
def dashboard(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

    total_games = db.scalar(select(func.count(Game.id))) or 0
    rankable_games = db.scalar(select(func.count(Game.id)).where(Game.is_rankable.is_(True))) or 0
    catalog_only_games = db.scalar(select(func.count(Game.id)).where(Game.content_type != "game")) or 0
    rating_snapshots = db.scalar(select(func.count(RatingSnapshot.id))) or 0
    source_snapshots = db.scalar(select(func.count(SourceSnapshot.id))) or 0

    total_visits = db.scalar(
        select(func.count(VisitEvent.id)).where(VisitEvent.created_at >= since)
    ) or 0
    unique_visitors = db.scalar(
        select(func.count(func.distinct(VisitEvent.visitor_id_hash))).where(VisitEvent.created_at >= since)
    ) or 0
    visits_today = db.scalar(
        select(func.count(VisitEvent.id)).where(VisitEvent.created_at >= today_start)
    ) or 0
    unique_today = db.scalar(
        select(func.count(func.distinct(VisitEvent.visitor_id_hash))).where(VisitEvent.created_at >= today_start)
    ) or 0

    path_count = func.count(VisitEvent.id).label("visits")
    top_pages = [
        {"path": path, "visits": visits}
        for path, visits in db.execute(
            select(VisitEvent.path, path_count)
            .where(VisitEvent.created_at >= since)
            .group_by(VisitEvent.path)
            .order_by(desc(path_count))
            .limit(10)
        ).all()
    ]

    daily_counts: dict[str, dict[str, int | set[str]]] = defaultdict(lambda: {"visits": 0, "visitors": set()})
    for event in db.scalars(select(VisitEvent).where(VisitEvent.created_at >= since)).all():
        key = event.created_at.date().isoformat()
        daily_counts[key]["visits"] = int(daily_counts[key]["visits"]) + 1
        visitors = daily_counts[key]["visitors"]
        if isinstance(visitors, set):
            visitors.add(event.visitor_id_hash)

    daily = []
    for i in range(days - 1, -1, -1):
        date_key = (now - timedelta(days=i)).date().isoformat()
        row = daily_counts.get(date_key, {"visits": 0, "visitors": set()})
        visitors = row["visitors"]
        daily.append({
            "date": date_key,
            "visits": int(row["visits"]),
            "visitors": len(visitors) if isinstance(visitors, set) else 0,
        })

    recent_visits = [
        {
            "path": event.path,
            "created_at": event.created_at.isoformat(),
            "visitor": event.visitor_id_hash[:10],
            "referrer": event.referrer,
            "screen": (
                f"{event.screen_width}x{event.screen_height}"
                if event.screen_width and event.screen_height
                else None
            ),
        }
        for event in db.scalars(
            select(VisitEvent)
            .order_by(VisitEvent.created_at.desc())
            .limit(20)
        ).all()
    ]

    return {
        "catalog": {
            "total_games": total_games,
            "rankable_games": rankable_games,
            "non_game_rows": catalog_only_games,
            "rating_snapshots": rating_snapshots,
            "source_snapshots": source_snapshots,
        },
        "traffic": {
            "days": days,
            "total_visits": total_visits,
            "unique_visitors": unique_visitors,
            "visits_today": visits_today,
            "unique_today": unique_today,
            "top_pages": top_pages,
            "daily": daily,
            "recent_visits": recent_visits,
        },
    }


# ── Data fill orchestration ─────────────────────────────────────────────────


@router.get("/data-fill/status")
def get_data_fill_status() -> dict[str, object]:
    return data_fill_status()


@router.post("/data-fill/run")
async def run_data_fill(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    target_total: int = Query(default=10000, ge=1, le=100000),
) -> dict[str, object]:
    run = queue_data_fill_run(force=force, target_total=target_total)
    background_tasks.add_task(
        execute_data_fill_run,
        int(run["id"]),
        force=force,
        target_total=target_total,
    )
    return {"status": "queued", "run": run}


@router.get("/primary-scores/status")
def get_primary_scores_status() -> dict[str, object]:
    return primary_score_coverage_status()


async def _execute_primary_scores_run(*, force: bool, limit: int) -> None:
    if HEAVY_JOB_LOCK.locked():
        return
    cfg = get_settings()
    async with HEAVY_JOB_LOCK:
        await primary_score_backfill_batch(
            limit=limit,
            force=force,
            inter_game_delay=cfg.DATA_FILL_INTER_GAME_DELAY,
        )


@router.post("/primary-scores/run")
async def run_primary_scores(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    limit: int = Query(default=10000, ge=1, le=100000),
) -> dict[str, object]:
    if HEAVY_JOB_LOCK.locked():
        raise HTTPException(status_code=409, detail="Another heavy job is already running.")
    background_tasks.add_task(_execute_primary_scores_run, force=force, limit=limit)
    return {"status": "started", "coverage": primary_score_coverage_status()}


# ── Per-source smoke test ─────────────────────────────────────────────────────


@router.get("/source-test/{source}")
async def source_test(
    source: SourceTest,
    q: str = Query(
        default="Portal 2",
        min_length=2,
        max_length=120,
        description="Title to search for",
    ),
) -> dict:
    """
    Run a live search against one source and return the normalized result.
    source: igdb | rawg | opencritic | steam | itad | cheapshark
    """
    source_name = source.value

    async def _run():
        match source_name:
            case "igdb":
                return await igdb_service.search_game(q)
            case "rawg":
                return await rawg_service.search_game(q)
            case "opencritic":
                return await opencritic_service.search_game(q)
            case "steam":
                # For Steam we test app ID lookup
                app_id = await steam_service.lookup_app_id("", q)
                if app_id:
                    details = await steam_service.get_app_details(app_id)
                    return details
                return None
            case "itad":
                itad_id = await itad_service.lookup_id(q)
                if itad_id:
                    return itad_service.normalize_for_external_id(itad_id, q)
                return None
            case "cheapshark":
                deals = await cheapshark_service.search_deals(q, limit=3)
                return [cheapshark_service.normalize_deal(d) for d in deals] if deals else None
            case _:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown source '{source_name}'. Valid: igdb, rawg, opencritic, steam, itad, cheapshark",
                )

    try:
        result = await asyncio.wait_for(_run(), timeout=20)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Source test for '{source_name}' timed out")

    if result is None:
        return {"source": source_name, "query": q, "found": False, "result": None}

    # Convert dataclass to dict for JSON serialization
    if hasattr(result, "__dataclass_fields__"):
        payload = dataclasses.asdict(result)
    elif isinstance(result, list):
        payload = [dataclasses.asdict(r) if hasattr(r, "__dataclass_fields__") else r for r in result]
    else:
        payload = result

    return {"source": source_name, "query": q, "found": True, "result": payload}


# ── External IDs ──────────────────────────────────────────────────────────────


@router.get("/external-ids/{game_id}")
def get_external_ids(game_id: int = Path(..., ge=1), db: Session = Depends(get_db)) -> dict:
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = db.scalars(select(ExternalId).where(ExternalId.game_id == game_id)).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "external_ids": [
            {
                "source": r.source,
                "external_id": r.external_id,
                "external_slug": r.external_slug,
                "external_url": r.external_url,
                "confidence": r.confidence,
                "is_primary": r.is_primary,
            }
            for r in rows
        ],
    }


@router.post("/match/external-ids")
async def match_external_ids(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Look up a game across all configured sources and upsert ExternalId rows.
    Uses the game title as search query.
    """
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    now = datetime.now(UTC)
    upserted: list[str] = []

    async def _match_igdb():
        result = await igdb_service.search_game(game.title)
        if result:
            _upsert_external_id(db, game_id, "IGDB", result.external_id, result.external_slug, result.external_url, now)
            upserted.append("IGDB")

    async def _match_rawg():
        result = await rawg_service.search_game(game.title)
        if result:
            _upsert_external_id(db, game_id, "RAWG", result.external_id, result.external_slug, None, now)
            upserted.append("RAWG")

    async def _match_itad():
        itad_id = await itad_service.lookup_id(game.title)
        if itad_id:
            _upsert_external_id(db, game_id, "ITAD", itad_id, None, None, now)
            upserted.append("ITAD")

    async def _match_steam():
        app_id = await steam_service.lookup_app_id(game.slug, game.title)
        if app_id:
            _upsert_external_id(
                db, game_id, "Steam", str(app_id), None,
                steam_service.store_url(app_id), now,
            )
            upserted.append("Steam")

    await asyncio.gather(
        _match_igdb(), _match_rawg(), _match_itad(), _match_steam(),
        return_exceptions=True,
    )
    db.commit()

    return {"game_id": game_id, "title": game.title, "matched": upserted}


def _upsert_external_id(
    db: Session,
    game_id: int,
    source: str,
    external_id: str,
    slug: str | None,
    url: str | None,
    now: datetime,
) -> None:
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game_id,
            ExternalId.source == source,
        )
    )
    if existing:
        existing.external_id = external_id
        existing.external_slug = slug
        existing.external_url = url
        existing.updated_at = now
    else:
        db.add(ExternalId(
            game_id=game_id,
            source=source,
            external_id=external_id,
            external_slug=slug,
            external_url=url,
            confidence=0.9,
            is_primary=True,
            created_at=now,
            updated_at=now,
        ))


# ── Rating snapshots ──────────────────────────────────────────────────────────


@router.get("/rating-snapshots/{game_id}")
def get_rating_snapshots(game_id: int = Path(..., ge=1), db: Session = Depends(get_db)) -> dict:
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = db.scalars(
        select(RatingSnapshot)
        .where(RatingSnapshot.game_id == game_id)
        .order_by(RatingSnapshot.fetched_at.desc())
    ).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "snapshots": [
            {
                "source": r.source,
                "score": r.score,
                "score_normalized": r.score_normalized,
                "rating_count": r.rating_count,
                "is_critic": r.is_critic,
                "is_user": r.is_user,
                "is_applicable": r.is_applicable,
                "confidence": r.confidence,
                "fetched_at": r.fetched_at.isoformat(),
                "raw_payload": r.raw_payload,
            }
            for r in rows
        ],
    }


@router.get("/source-snapshots/{game_id}")
def get_source_snapshots(game_id: int = Path(..., ge=1), db: Session = Depends(get_db)) -> dict:
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = db.scalars(
        select(SourceSnapshot)
        .where(SourceSnapshot.query == game.title)
        .order_by(SourceSnapshot.fetched_at.desc())
    ).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "snapshots": [
            {
                "source": r.source,
                "endpoint": r.endpoint,
                "query": r.query,
                "external_id": r.external_id,
                "status_code": r.status_code,
                "fetched_at": r.fetched_at.isoformat(),
                "raw_payload": r.raw_payload,
            }
            for r in rows
        ],
    }


# ── Deduplication / reclassification ─────────────────────────────────────────


@router.post("/consolidate")
def admin_consolidate(db: Session = Depends(get_db)) -> dict:
    """
    Reclassify all games by inferred content_type (DLC / demo / software …),
    then merge duplicate game rows into a single canonical record.
    """
    reclassified = 0
    all_games = list(db.scalars(select(Game)).all())
    parent_titles = frozenset(g.title.strip().lower() for g in all_games)
    for game in all_games:
        inferred = infer_content_type_with_parent(game, parent_titles)
        if game.content_type != inferred:
            game.content_type = inferred
            reclassified += 1
    if reclassified:
        db.commit()

    result = consolidate_duplicate_games(db)
    return {
        "reclassified": reclassified,
        "merged_groups": result["merged_groups"],
        "removed": result["removed"],
    }


# ── Price import ──────────────────────────────────────────────────────────────


@router.post("/import/prices/itad")
async def import_prices_itad(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    country: str = Query(default="EU", min_length=2, max_length=3, pattern=r"^[A-Za-z]{2,3}$", description="Region code (EU, US, ...)"),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch current ITAD prices for a game and store in price_snapshots."""
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if not itad_service.is_configured():
        raise HTTPException(status_code=503, detail="ITAD_API_KEY not configured")

    price_data = await itad_service.fetch_price_data(game.title, country=country)
    if not price_data:
        return {"game_id": game_id, "stored": False, "reason": "No ITAD price data found"}

    now = datetime.now(UTC)
    snap = PriceSnapshot(
        game_id=game_id,
        source="ITAD",
        store=price_data.store,
        region=country,
        currency=price_data.currency,
        list_price=price_data.list_price,
        sale_price=price_data.sale_price,
        discount_percent=price_data.discount_percent,
        historical_low=price_data.historical_low,
        historical_low_date=price_data.historical_low_date,
        is_free=price_data.is_free,
        is_subscription_included=price_data.is_subscription_included,
        subscription_service=price_data.subscription_service,
        itad_id=price_data.itad_id,
        fetched_at=now,
        created_at=now,
    )
    db.add(snap)
    db.commit()

    return {
        "game_id": game_id,
        "stored": True,
        "store": price_data.store,
        "list_price": price_data.list_price,
        "sale_price": price_data.sale_price,
        "currency": price_data.currency,
        "historical_low": price_data.historical_low,
        "is_free": price_data.is_free,
        "subscription": price_data.subscription_service,
    }


@router.post("/import/prices/cheapshark")
async def import_prices_cheapshark(
    game_id: int = Query(..., ge=1, description="GameMetrix game ID"),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch cheapest CheapShark deal for a game and store in price_snapshots."""
    game = db.scalar(select(Game).where(Game.id == game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    deals = await cheapshark_service.search_deals(game.title, limit=5)
    if not deals:
        return {"game_id": game_id, "stored": False, "reason": "No CheapShark deals found"}

    best = min(deals, key=lambda d: float(d.get("salePrice", 9999)))
    normalized = cheapshark_service.normalize_deal(best)

    now = datetime.now(UTC)
    snap = PriceSnapshot(
        game_id=game_id,
        source="CheapShark",
        store=normalized.raw.get("store_name", ""),
        region="US",
        currency="USD",
        list_price=normalized.list_price,
        sale_price=normalized.sale_price,
        discount_percent=int(normalized.raw.get("savings_pct", 0)),
        raw_payload=normalized.raw,
        fetched_at=now,
        created_at=now,
    )
    db.add(snap)
    db.commit()

    return {
        "game_id": game_id,
        "stored": True,
        "store": normalized.raw.get("store_name"),
        "list_price": normalized.list_price,
        "sale_price": normalized.sale_price,
        "currency": "USD",
    }
