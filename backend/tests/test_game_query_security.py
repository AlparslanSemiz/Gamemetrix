import asyncio
import re
from datetime import UTC, date, datetime

from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game, PriceSnapshot
from app.schemas import CatalogGameRead
from app.services.catalog_projection import catalog_load_options
from app.services import game_query, trailer_cache


def test_advanced_catalog_filters_and_sorts_stay_in_postgres() -> None:
    statement = game_query.apply_advanced_filters(
        select(Game),
        game_query.CatalogFilters(
            genre="RPG",
            developer="Studio",
            publisher="Publisher",
            platform="Steam",
            min_ratings=10,
            max_ratings=10_000,
            has_award=True,
            min_live_sources=2,
            require_critic=True,
            player_mode="coop",
            playtime_min_hours=2,
            playtime_max_hours=100,
        ),
    )
    statement = game_query.apply_sort(statement, "review_count", "desc").limit(24).offset(48)
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "jsonb_array_elements" in sql
    assert "ORDER BY (SELECT" in sql
    assert "LIMIT 24 OFFSET 48" in sql


def test_catalog_count_uses_index_only_friendly_count_star() -> None:
    statement = game_query.build_catalog_count_query(
        "game", None, None, None, None, None, "all",
    )
    sql = str(statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))

    assert "count(*)" in sql.lower()
    assert "count(games.id)" not in sql.lower()


def test_catalog_projection_omits_detail_only_json_columns() -> None:
    statement = select(Game).options(*catalog_load_options(include_prices=False))
    sql = str(statement.compile(dialect=postgresql.dialect()))

    for column in (
        "summary",
        "screenshots",
        "system_requirements",
        "dlcs",
        "similar_games",
    ):
        assert re.search(rf"\bgames\.{column}\b", sql) is None
    for column in ("games.id", "games.slug", "games.source_scores"):
        assert column in sql


def test_catalog_projection_serializes_without_lazy_detail_queries() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Game.__table__, PriceSnapshot.__table__],
    )
    now = datetime.now(UTC)
    with Session(engine) as session:
        game = Game(
            title="Projection Test",
            slug="projection-test",
            summary="A full detail summary that should not be selected.",
            summary_short="A short card summary.",
            cover_url="https://example.test/cover.jpg",
            release_date=date(2025, 1, 1),
            release_year=2025,
            metrix_score=80,
            critic_score=81,
            user_score=79,
            genres=["RPG"],
            platforms=["PC"],
            source_scores=[],
        )
        session.add(game)
        session.flush()
        session.add(PriceSnapshot(
            game_id=game.id,
            source="itad",
            store="Steam",
            region="US",
            currency="USD",
            is_free=False,
            is_subscription_included=False,
            fetched_at=now,
            created_at=now,
        ))
        session.commit()

    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many:
            statements.append(statement),
    )
    with Session(engine) as session:
        game = session.scalars(
            select(Game).options(*catalog_load_options(include_prices=False)),
        ).one()
        payload = CatalogGameRead.model_validate(game)

    assert payload.price_snapshots == []
    assert len(statements) == 1
    for column in ("summary", "screenshots", "system_requirements", "dlcs", "similar_games"):
        assert re.search(rf"\bgames\.{column}\b", statements[0]) is None


def test_trailer_lookups_are_cached_and_coalesced(monkeypatch) -> None:
    calls = 0

    async def fake_lookup(title: str) -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return f"video-for-{title}"

    async def scenario() -> None:
        trailer_cache.clear_trailer_cache()
        monkeypatch.setattr(trailer_cache, "find_trailer_video_id", fake_lookup)
        results = await asyncio.gather(*(
            trailer_cache.cached_trailer_video_id("same-game", "Same Game")
            for _ in range(8)
        ))
        assert results == ["video-for-Same Game"] * 8

    asyncio.run(scenario())
    assert calls == 1
