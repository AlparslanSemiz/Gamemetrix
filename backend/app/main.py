import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from .database import Base, SessionLocal, engine
from .models import Game, infer_content_type
from .seed import patch_roguelike_genres, seed_games
from .routers import admin
from .routers.games import router as games_router
from .routers.imports import router as imports_router
from .routers.ratings import router as ratings_router
from .services.background import daily_refresh_loop


# ── SQLite column migrations ───────────────────────────────────────────────────


def _add_column_if_missing(conn, table: str, column: str, col_type: str) -> None:
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.commit()
    except Exception:
        pass  # column already exists


def _run_migrations(conn) -> None:
    migrations = [
        ("games", "developer", "VARCHAR(200)"),
        ("games", "publisher", "VARCHAR(200)"),
        ("games", "playtime_minutes", "INTEGER DEFAULT 0"),
        ("games", "metacritic_score", "INTEGER"),
        ("games", "image_url", "VARCHAR(500)"),
        ("games", "ratings_refreshed_at", "TIMESTAMP"),
        ("games", "content_type", "VARCHAR(40) DEFAULT 'game'"),
        ("games", "award_count", "INTEGER DEFAULT 0"),
        ("games", "award_nominations", "INTEGER DEFAULT 0"),
        ("games", "goty_year", "INTEGER"),
    ]
    for table, column, col_type in migrations:
        _add_column_if_missing(conn, table, column, col_type)


# ── Startup seed / classify ────────────────────────────────────────────────────


def _seed_and_classify(db) -> None:
    seed_games(db)
    patch_roguelike_genres(db)
    for game in db.scalars(select(Game)).all():
        inferred = infer_content_type(game)
        if game.content_type != inferred:
            game.content_type = inferred
    db.commit()


# ── App lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        _run_migrations(conn)
    with SessionLocal() as db:
        _seed_and_classify(db)

    refresh_task = asyncio.create_task(daily_refresh_loop())
    try:
        yield
    finally:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass


# ── App wiring ────────────────────────────────────────────────────────────────


app = FastAPI(title="GameMetrix API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games_router)
app.include_router(imports_router)
app.include_router(ratings_router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
