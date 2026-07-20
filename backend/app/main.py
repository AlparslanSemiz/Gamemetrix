import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import select

from sqlalchemy.orm import Session
from .config import get_settings
from .database import SessionLocal
from .rate_limit import limiter
from .integrations.steam import fetch_steam_screenshots
from .integrations.sync import calculate_metrix_score, compute_rank_fields
from .models import Game, infer_content_type, infer_content_type_with_parent
from .seed import seed_games
from .routers import admin
from .routers.analytics import router as analytics_router
from .routers.auth import router as auth_router
from .routers.account import router as account_router
from .routers.games import router as games_router
from .routers.imports import router as imports_router
from .routers.ratings import router as ratings_router
from .routers.seo import router as seo_router
from .services.admin_audit import audit_admin_request
from .services.background import (
    daily_refresh_loop,
    hltb_backfill_loop,
    metadata_backfill_loop,
    raw_analytics_retention_loop,
)
from .services.data_fill import data_fill_loop
from .services.deduplication import consolidate_duplicate_games
from .services.seo import refresh_catalog_seo_states
from .services.notification_digest import notification_digest_loop


log = logging.getLogger(__name__)
settings = get_settings()
settings.validate()


# ── Startup seed / classify ────────────────────────────────────────────────────


def _reclassify_and_rescore(db: Session) -> None:
    changed: list[Game] = []
    all_games = db.scalars(select(Game)).all()
    parent_titles = frozenset(g.title.strip().lower() for g in all_games)
    for game in all_games:
        inferred = infer_content_type_with_parent(game, parent_titles)
        dirty = False
        if game.content_type != inferred:
            game.content_type = inferred
            dirty = True
        new_score = calculate_metrix_score(game.source_scores)
        rank_score, is_rankable, _ = compute_rank_fields(game)
        if game.metrix_score != new_score or game.rank_score != rank_score or game.is_rankable != is_rankable:
            game.metrix_score = new_score
            game.rank_score = rank_score
            game.is_rankable = is_rankable
            dirty = True
        if dirty:
            changed.append(game)
    if changed:
        db.add_all(changed)
    db.commit()


def _seed_and_classify(db: Session) -> None:
    seed_games(db)
    _reclassify_and_rescore(db)
    # Both passes walk the whole catalog. Releasing the first one's objects before the
    # second loads its own keeps one copy of the catalog in memory instead of two, which
    # was a large part of the startup peak that OOM-killed the container. Each pass
    # commits independently and both are idempotent recomputations, so a crash between
    # them is repaired by the next boot rather than leaving a half-written state.
    db.expunge_all()
    refresh_catalog_seo_states(db)
    db.commit()
    result = consolidate_duplicate_games(db)
    if result["removed"]:
        refresh_catalog_seo_states(db)
        db.commit()
        log.info(
            "Consolidated duplicate games: %s groups, %s rows removed",
            result["merged_groups"],
            result["removed"],
        )


# ── App lifespan ───────────────────────────────────────────────────────────────


async def _background_startup() -> None:
    """Runs in a thread after the server is ready — does not block the event loop."""
    await asyncio.sleep(2)
    loop = asyncio.get_event_loop()
    try:
        def _classify() -> None:
            with SessionLocal() as db:
                _seed_and_classify(db)
        await loop.run_in_executor(None, _classify)
    except Exception:
        log.exception("Background startup classify failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Seed only — fast, must run before serving so the games table is populated.
    with SessionLocal() as db:
        seed_games(db)

    # Provider budgets (limits, aliases, windows) come from Settings, so every
    # process shares them — see config.provider_daily_limits().
    startup_task = asyncio.create_task(_background_startup())
    refresh_task = asyncio.create_task(daily_refresh_loop())
    metadata_task = asyncio.create_task(metadata_backfill_loop())
    hltb_task = asyncio.create_task(hltb_backfill_loop())
    data_fill_task = asyncio.create_task(data_fill_loop())
    notification_task = asyncio.create_task(notification_digest_loop())
    retention_task = asyncio.create_task(raw_analytics_retention_loop())
    try:
        yield
    finally:
        startup_task.cancel()
        refresh_task.cancel()
        metadata_task.cancel()
        hltb_task.cancel()
        data_fill_task.cancel()
        notification_task.cancel()
        retention_task.cancel()
        for task in (
            startup_task, refresh_task, metadata_task, hltb_task,
            data_fill_task, notification_task, retention_task,
        ):
            try:
                await task
            except asyncio.CancelledError:
                pass


# ── App wiring ────────────────────────────────────────────────────────────────


app = FastAPI(
    title="GameMetrix API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def private_api_cache_control(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/admin/")) or request.url.path == "/admin":
        response.headers["Cache-Control"] = "private, no-store"
    return response


app.middleware("http")(audit_admin_request)

app.include_router(auth_router)
app.include_router(account_router)
app.include_router(analytics_router)
app.include_router(games_router)
app.include_router(imports_router)
app.include_router(ratings_router)
app.include_router(seo_router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
