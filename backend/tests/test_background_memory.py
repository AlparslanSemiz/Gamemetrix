import asyncio
from contextlib import AbstractContextManager
from types import SimpleNamespace

import pytest

from app.services import background


class _FakeSession(AbstractContextManager):
    def get(self, _model, game_id: int):
        return SimpleNamespace(id=game_id)

    def commit(self) -> None:
        pass

    def __exit__(self, *_args) -> None:
        pass


@pytest.mark.asyncio
async def test_refresh_all_games_bounds_concurrent_work(monkeypatch) -> None:
    game_ids = list(range(1, 201))
    monkeypatch.setattr(
        background,
        "_rating_refresh_plan",
        lambda force: (game_ids, 250),
    )
    monkeypatch.setattr(background, "SessionLocal", _FakeSession)

    active = 0
    peak_active = 0

    async def fake_refresh(_db, _game, **_kwargs) -> None:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0)
        active -= 1

    monkeypatch.setattr(background, "refresh_game_sources", fake_refresh)
    monkeypatch.setattr(background, "game_needs_rating_refresh", lambda _game, _now: True)

    from app.services import seo

    monkeypatch.setattr(seo, "refresh_catalog_seo_states", lambda _db: None)

    result = await background.refresh_all_games(
        concurrency=3,
        force=False,
        inter_game_delay=0,
    )

    assert peak_active == 3
    assert result == {"enriched": 200, "skipped": 50}
