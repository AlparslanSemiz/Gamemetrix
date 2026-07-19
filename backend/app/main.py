import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from sqlalchemy.orm import Session
from .config import get_settings
from .database import Base, SessionLocal, engine
from .integrations.rate_limiter import get_rate_limiter
from .rate_limit import limiter
from .integrations.steam import fetch_steam_screenshots
from .integrations.sync import calculate_metrix_score, compute_rank_fields
from .models import Game, infer_content_type, infer_content_type_with_parent
from .seed import seed_games
from .routers import admin
from .routers.analytics import router as analytics_router
from .routers.auth import router as auth_router
from .routers.games import router as games_router
from .routers.imports import router as imports_router
from .routers.ratings import router as ratings_router
from .services.background import daily_refresh_loop, metadata_backfill_loop
from .services.data_fill import data_fill_loop
from .services.deduplication import consolidate_duplicate_games


log = logging.getLogger(__name__)
settings = get_settings()


# ── Lightweight PostgreSQL migrations ─────────────────────────────────────────


def _add_column_if_missing(conn: Connection, table: str, column: str, col_type: str) -> None:
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
    conn.commit()


def _add_index_if_missing(conn: Connection, index_name: str, table: str, columns: str, unique: bool = False) -> None:
    unique_kw = "UNIQUE " if unique else ""
    conn.execute(text(f"CREATE {unique_kw}INDEX IF NOT EXISTS {index_name} ON {table} ({columns})"))
    conn.commit()


def _run_migrations(conn: Connection) -> None:
    migrations = [
        ("games", "developer", "VARCHAR(200)"),
        ("games", "publisher", "VARCHAR(200)"),
        ("games", "playtime_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_id", "INTEGER"),
        ("games", "hltb_url", "VARCHAR(500)"),
        ("games", "hltb_main_story_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_main_extra_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_completionist_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_all_styles_minutes", "INTEGER DEFAULT 0"),
        ("games", "hltb_refreshed_at", "TIMESTAMP"),
        ("games", "proton_tier", "VARCHAR(16)"),
        ("games", "proton_score", "FLOAT"),
        ("games", "metacritic_score", "INTEGER"),
        ("games", "image_url", "VARCHAR(500)"),
        ("games", "website_url", "VARCHAR(500)"),
        ("games", "ratings_refreshed_at", "TIMESTAMP"),
        ("games", "metadata_refreshed_at", "TIMESTAMP"),
        ("games", "content_type", "VARCHAR(40) DEFAULT 'game'"),
        ("games", "award_count", "INTEGER DEFAULT 0"),
        ("games", "award_nominations", "INTEGER DEFAULT 0"),
        ("games", "goty_year", "INTEGER"),
        ("games", "awards", "JSON DEFAULT '[]'::json"),
        ("games", "summary_short", "TEXT"),
        ("games", "screenshots", "JSON DEFAULT '[]'::json"),
        ("games", "system_requirements", "JSON DEFAULT '[]'::json"),
        ("games", "dlcs", "JSON DEFAULT '[]'::json"),
        ("games", "similar_games", "JSON DEFAULT '[]'::json"),
        ("games", "early_access_date", "DATE"),
        ("games", "official_release_date", "DATE"),
        ("games", "rank_score", "FLOAT NOT NULL DEFAULT 0.0"),
        ("games", "is_rankable", "BOOLEAN NOT NULL DEFAULT false"),
    ]
    for table, column, col_type in migrations:
        _add_column_if_missing(conn, table, column, col_type)

    _add_index_if_missing(conn, "ix_games_rank_score", "games", "rank_score")
    _add_index_if_missing(conn, "ix_games_content_type", "games", "content_type")
    _add_index_if_missing(conn, "ix_games_content_type_rank_score", "games", "content_type, rank_score DESC")
    _add_index_if_missing(conn, "ix_games_hltb_id", "games", "hltb_id")


# ── Startup seed / classify ────────────────────────────────────────────────────


def _seed_and_classify(db: Session) -> None:
    seed_games(db)
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
    result = consolidate_duplicate_games(db)
    if result["removed"]:
        log.info(
            "Consolidated duplicate games: %s groups, %s rows removed",
            result["merged_groups"],
            result["removed"],
        )


def _steam_media_url(app_id: int, cover: str) -> str:
    if cover.startswith("http"):
        return cover
    return f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{cover}"


async def _repair_known_media(db: Session) -> None:
    known_media: tuple[tuple[tuple[str, ...], tuple[str, ...], int, str], ...] = (
        (("disco-elysium-the-final-cut",), ("Disco Elysium - The Final Cut",), 632470, "capsule_616x353.jpg"),
        (("resident-evil-4-remake",), ("Resident Evil 4 Remake",), 2050650, "capsule_616x353.jpg"),
        (("resident-evil-4",), ("Resident Evil 4",), 254700, "library_hero.jpg"),
        (
            ("the-last-of-us-part-2", "the-last-of-us-part-ii-remastered"),
            ("The Last of Us Part II Remastered",),
            2531310,
            "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2531310/header.jpg",
        ),
    )
    for slugs, titles, app_id, cover_file in known_media:
        game = db.scalar(select(Game).where(Game.slug.in_(slugs)))
        if game is None:
            game = db.scalar(select(Game).where(Game.title.in_(titles)))
        if game is None:
            continue
        expected_cover = _steam_media_url(app_id, cover_file)
        if game.cover_url != expected_cover:
            game.cover_url = expected_cover
            game.image_url = expected_cover

        screenshots = game.screenshots or []
        has_wrong_steam_media = any(
            "steamcdn-a.akamaihd.net/steam/apps/" in url and f"/{app_id}/" not in url
            for url in screenshots
        )
        if not screenshots or has_wrong_steam_media:
            fresh = await fetch_steam_screenshots(app_id)
            if fresh:
                game.screenshots = fresh
    db.commit()


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
    try:
        with SessionLocal() as db:
            await _repair_known_media(db)
    except Exception:
        log.exception("Background startup media repair failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        _run_migrations(conn)

    # Seed only — fast, must run before serving so the games table is populated.
    with SessionLocal() as db:
        seed_games(db)

    # Configure per-source daily request budgets from environment / .env
    cfg = get_settings()
    limiter = get_rate_limiter()
    limiter.set_limit("OpenCritic", cfg.OPENCRITIC_DAILY_LIMIT)
    limiter.set_limit("IGDB", cfg.IGDB_DAILY_LIMIT)
    limiter.set_limit("RAWG", cfg.RAWG_DAILY_LIMIT)
    # Metacritic scores are fetched through the RAWG API with the same key, so
    # they must share one budget — separate budgets let combined traffic reach
    # 2x the daily limit and exhaust RAWG's 20k/month quota mid-month.
    limiter.share_budget("Metacritic", "RAWG")
    limiter.set_limit("Steam", cfg.STEAM_DAILY_LIMIT)
    limiter.set_limit("SteamSpy", cfg.STEAMSPY_DAILY_LIMIT)
    limiter.set_limit("CheapShark", cfg.CHEAPSHARK_DAILY_LIMIT)
    limiter.set_limit("FreeToGame", cfg.FREETOGAME_DAILY_LIMIT)
    limiter.set_limit("ITAD", cfg.ITAD_DAILY_LIMIT)

    startup_task = asyncio.create_task(_background_startup())
    refresh_task = asyncio.create_task(daily_refresh_loop())
    metadata_task = asyncio.create_task(metadata_backfill_loop())
    data_fill_task = asyncio.create_task(data_fill_loop())
    try:
        yield
    finally:
        startup_task.cancel()
        refresh_task.cancel()
        metadata_task.cancel()
        data_fill_task.cancel()
        for task in (startup_task, refresh_task, metadata_task, data_fill_task):
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
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(games_router)
app.include_router(imports_router)
app.include_router(ratings_router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
