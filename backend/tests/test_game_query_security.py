import asyncio

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Game
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
