from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import asc, desc, select, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import Game
from .schemas import (
    FacetsResponse,
    GameListResponse,
    GameRead,
    GameSort,
    ImportResponse,
    MultiImportResponse,
    ProviderStatus,
    RecalculateResponse,
    ScoreWeightsResponse,
    ScoreWeightsUpdate,
    SortDirection,
)
from .seed import seed_games
from .integrations.provider_status import get_provider_statuses
from .integrations.cheapshark import import_cheapshark_deals
from .integrations.free_to_game import import_free_to_game_games
from .integrations.rawg import import_rawg_games
from .integrations.steamspy import import_steamspy_games
from .integrations.sync import SOURCE_WEIGHTS, calculate_metrix_score, refresh_game_sources

CRITIC_SOURCES = {"Metacritic", "OpenCritic", "IGDB"}


def _source_score(game: Game, source_name: str) -> float:
    for score in game.source_scores:
        if str(score.get("source", "")).lower() == source_name.lower():
            return float(score.get("score", 0))
    return 0.0


def _review_count(game: Game) -> int:
    return sum(int(score.get("review_count", 0)) for score in game.source_scores)


def _add_column_if_missing(conn, table: str, column: str, col_type: str) -> None:
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.commit()
    except Exception:
        pass  # Column already exists


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite column migrations (no-op if columns already exist).
    with engine.connect() as conn:
        _add_column_if_missing(conn, "games", "developer", "VARCHAR(200)")
        _add_column_if_missing(conn, "games", "publisher", "VARCHAR(200)")
        _add_column_if_missing(conn, "games", "playtime_minutes", "INTEGER DEFAULT 0")

    with SessionLocal() as db:
        seed_games(db)

    yield


app = FastAPI(title="GameMetrix API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/games", response_model=GameListResponse)
def list_games(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=2),
    genre: str | None = None,
    year_min: int | None = Query(default=None, ge=1970, le=2100),
    year_max: int | None = Query(default=None, ge=1970, le=2100),
    platform: str | None = None,
    developer: str | None = None,
    publisher: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    min_ratings: int | None = Query(default=None, ge=0),
    min_live_sources: int | None = Query(default=None, ge=0, le=10),
    require_critic: bool = False,
    sort: GameSort = "metrix_score",
    direction: SortDirection = "desc",
    limit: int = Query(default=120, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GameListResponse:
    query = select(Game)

    if q:
        query = query.where(Game.title.ilike(f"%{q}%"))
    if year_min is not None:
        query = query.where(Game.release_year >= year_min)
    if year_max is not None:
        query = query.where(Game.release_year <= year_max)
    if min_score is not None:
        query = query.where(Game.metrix_score >= min_score)
    if max_score is not None:
        query = query.where(Game.metrix_score <= max_score)

    if sort == "title":
        query = query.order_by(asc(Game.title))
    elif sort == "release_year":
        query = query.order_by(
            desc(Game.release_year) if direction == "desc" else asc(Game.release_year),
            desc(Game.metrix_score),
        )
    elif sort == "critic_score":
        query = query.order_by(
            desc(Game.critic_score) if direction == "desc" else asc(Game.critic_score)
        )
    elif sort == "user_score":
        query = query.order_by(
            desc(Game.user_score) if direction == "desc" else asc(Game.user_score)
        )
    else:
        query = query.order_by(
            desc(Game.metrix_score) if direction == "desc" else asc(Game.metrix_score)
        )

    games = list(db.scalars(query).all())

    if genre:
        games = [game for game in games if genre in game.genres]

    if developer:
        games = [
            game
            for game in games
            if game.developer and game.developer.lower() == developer.lower()
        ]

    if publisher:
        games = [
            game
            for game in games
            if game.publisher and game.publisher.lower() == publisher.lower()
        ]

    if platform:
        platform_terms = [platform.lower()]
        if platform.lower() == "steam":
            platform_terms.append("pc")
        games = [
            game
            for game in games
            if any(
                term in stored_platform.lower()
                for stored_platform in game.platforms
                for term in platform_terms
            )
        ]

    if min_ratings:
        games = [
            g for g in games
            if sum(int(s.get("review_count", 0)) for s in g.source_scores if s.get("status") == "live") >= min_ratings
        ]

    if min_live_sources:
        games = [
            g for g in games
            if sum(1 for s in g.source_scores if s.get("status") == "live" and float(s.get("score", 0)) > 0) >= min_live_sources
        ]

    if require_critic:
        games = [
            g for g in games
            if any(
                str(s.get("source")) in CRITIC_SOURCES
                and s.get("status") == "live"
                and float(s.get("score", 0)) > 0
                for s in g.source_scores
            )
        ]

    if sort in {"metacritic_score", "opencritic_score", "steam_score", "review_count"}:
        source_map = {
            "metacritic_score": "Metacritic",
            "opencritic_score": "OpenCritic",
            "steam_score": "Steam",
        }
        if sort == "review_count":
            games.sort(key=_review_count, reverse=direction == "desc")
        else:
            games.sort(
                key=lambda game: _source_score(game, source_map[sort]),
                reverse=direction == "desc",
            )
    elif sort == "title" and direction == "desc":
        games.sort(key=lambda game: game.title.lower(), reverse=True)

    total = len(games)
    games = games[offset : offset + limit]

    return GameListResponse(games=games, total=total)


@app.get("/api/games/{slug}", response_model=GameRead)
def get_game(slug: str, db: Session = Depends(get_db)) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return game


@app.post("/api/games/{slug}/refresh-scores", response_model=GameRead)
async def refresh_game(slug: str, db: Session = Depends(get_db)) -> Game:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return await refresh_game_sources(db, game)


@app.get("/api/facets", response_model=FacetsResponse)
def get_facets(db: Session = Depends(get_db)) -> FacetsResponse:
    import datetime

    current_year = datetime.date.today().year
    games = db.scalars(select(Game)).all()

    genres = sorted({genre for game in games for genre in game.genres})
    # Cap at current year to exclude unannounced/future entries from slider range.
    years = sorted(
        {game.release_year for game in games if game.release_year <= current_year},
        reverse=True,
    )
    platforms = {platform for game in games for platform in game.platforms}
    platform_filters = set(platforms)
    if any(platform in platforms for platform in ["PC", "Steam"]):
        platform_filters.add("Steam")
    if any("PlayStation" in platform for platform in platforms):
        platform_filters.add("PlayStation")
    if any("Xbox" in platform for platform in platforms):
        platform_filters.add("Xbox")
    if any(
        platform in platforms
        for platform in ["Nintendo Switch", "Nintendo", "Wii", "Wii U"]
    ):
        platform_filters.add("Nintendo")

    return FacetsResponse(genres=genres, years=years, platforms=sorted(platform_filters))


@app.get("/api/integrations/status", response_model=list[ProviderStatus])
def integration_status() -> list[dict[str, str]]:
    return get_provider_statuses()


@app.get("/api/score-weights", response_model=ScoreWeightsResponse)
def get_score_weights() -> dict[str, dict[str, float]]:
    return {"weights": SOURCE_WEIGHTS}


@app.put("/api/score-weights", response_model=ScoreWeightsResponse)
def update_score_weights(payload: ScoreWeightsUpdate) -> dict[str, dict[str, float]]:
    for source, value in payload.weights.items():
        SOURCE_WEIGHTS[source] = max(0.0, min(float(value), 1.0))
    return {"weights": SOURCE_WEIGHTS}


@app.post("/api/score-weights/recalculate", response_model=RecalculateResponse)
def recalculate_scores(db: Session = Depends(get_db)) -> dict[str, int]:
    games = db.query(Game).all()
    for game in games:
        game.metrix_score = calculate_metrix_score(game.source_scores)
    db.commit()
    return {"recalculated": len(games)}


@app.post("/api/import/rawg", response_model=ImportResponse)
async def import_from_rawg(
    target: int = Query(default=2000, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    try:
        return await import_rawg_games(db, target=target)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/import/free-to-game", response_model=ImportResponse)
async def import_from_free_to_game(
    target: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_free_to_game_games(db, target=target)


@app.post("/api/import/cheapshark", response_model=ImportResponse)
async def import_from_cheapshark(
    target: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_cheapshark_deals(db, target=target)


@app.post("/api/import/steamspy", response_model=ImportResponse)
async def import_from_steamspy(
    target: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_steamspy_games(db, target=target)


@app.post("/api/import/free-sources", response_model=MultiImportResponse)
async def import_from_free_sources(
    free_to_game_target: int = Query(default=500, ge=1, le=1000),
    cheapshark_target: int = Query(default=300, ge=1, le=1000),
    steamspy_target: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    sources = {
        "FreeToGame": await import_free_to_game_games(db, target=free_to_game_target),
        "CheapShark": await import_cheapshark_deals(db, target=cheapshark_target),
        "SteamSpy": await import_steamspy_games(db, target=steamspy_target),
    }

    return {
        "imported": sum(int(result["imported"]) for result in sources.values()),
        "skipped": sum(int(result["skipped"]) for result in sources.values()),
        "sources": sources,
    }
