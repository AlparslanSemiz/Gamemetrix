"""Counting cache, pool-exhaustion 503, readiness, API bounds, genre filter."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Game
from app.rate_limit import limiter
from app.services import count_cache, game_query


def test_count_cache_serves_repeats_and_expires() -> None:
    count_cache.clear_count_cache()
    clock = {"t": 1000.0}
    runs: list[int] = []

    def compute() -> int:
        runs.append(1)
        return 42

    key = count_cache.count_cache_key("games", [("genre", "RPG"), ("offset", "0"), ("sort", "x")])
    paged = count_cache.count_cache_key("games", [("offset", "48"), ("genre", "RPG"), ("limit", "9")])
    assert key == paged  # paging/sorting never change the total
    assert count_cache.cached_count(key, compute, now=lambda: clock["t"]) == 42
    assert count_cache.cached_count(paged, compute, now=lambda: clock["t"] + 299) == 42
    assert len(runs) == 1
    assert count_cache.cached_count(key, compute, now=lambda: clock["t"] + 301) == 42
    assert len(runs) == 2


def test_count_cache_is_bounded() -> None:
    count_cache.clear_count_cache()
    for index in range(count_cache.COUNT_CACHE_MAX_ENTRIES + 20):
        count_cache.cached_count(("k", index), lambda: 1)
    assert len(count_cache._cache) == count_cache.COUNT_CACHE_MAX_ENTRIES


@pytest.mark.asyncio
async def test_pool_exhaustion_becomes_a_retryable_503() -> None:
    from app.main import _pool_exhausted

    response = await _pool_exhausted(None, PoolTimeoutError("QueuePool limit reached"))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
needs_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL or not TEST_DATABASE_URL.rsplit("/", 1)[-1].endswith("_test"),
    reason="Set TEST_DATABASE_URL to a PostgreSQL database whose name ends with _test.",
)


@pytest.fixture()
def pg_client(monkeypatch):
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.main.SessionLocal", sessions)
    count_cache.clear_count_cache()
    game_query._genre_lookup.clear()
    limiter.enabled = False
    client = TestClient(app)
    yield client, sessions
    limiter.enabled = True
    client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _game(slug: str, genres: list[str]) -> Game:
    from datetime import date

    return Game(
        title=slug, slug=slug, summary="s", cover_url="c", release_date=date(2020, 1, 1),
        release_year=2020, critic_score=50, user_score=50, metrix_score=50,
        genres=genres, platforms=["PC"], source_scores=[],
    )


@needs_postgres
def test_readiness_needs_database_and_catalog(pg_client) -> None:
    client, sessions = pg_client
    empty = client.get("/health/ready")
    assert empty.status_code == 503 and empty.json()["status"] == "empty-catalog"
    with sessions() as db:
        db.add(_game("ready-game", ["RPG"]))
        db.commit()
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json() == {"status": "ok", "database": True}
    assert client.get("/health").json() == {"status": "ok"}


@needs_postgres
def test_catalog_bounds_genre_case_and_cached_total(pg_client) -> None:
    client, sessions = pg_client
    with sessions() as db:
        db.add_all([_game("rpg-one", ["Role-Playing"]), _game("shooter", ["FPS"])])
        db.commit()

    assert client.get("/api/games", params={"offset": 2401}).status_code == 422
    assert client.get("/api/games", params={"limit": 51}).status_code == 422
    assert client.get("/api/catalog/games", params={"limit": 101}).status_code == 422
    assert client.get("/api/catalog/games", params={"offset": 2401}).status_code == 422
    assert client.get("/api/games", params={"offset": 2400, "limit": 50}).status_code == 200

    for spelling in ("role-playing", "ROLE-PLAYING", "Role-Playing"):
        body = client.get("/api/games", params={"genre": spelling}).json()
        assert [g["slug"] for g in body["games"]] == ["rpg-one"]
        assert body["total"] == 1
    assert client.get("/api/games", params={"genre": "nonexistent"}).json()["total"] == 0

    with sessions() as db:
        db.add(_game("rpg-two", ["Role-Playing"]))
        db.commit()
    # Paging the same filter reuses the cached total (staleness is bounded to five minutes).
    page = client.get("/api/games", params={"genre": "Role-Playing", "limit": 1, "offset": 1}).json()
    assert page["total"] == 1
    count_cache.clear_count_cache()
    assert client.get("/api/games", params={"genre": "Role-Playing"}).json()["total"] == 2
