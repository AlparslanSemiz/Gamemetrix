import asyncio
from types import SimpleNamespace

from app.services.data_fill import stages


def test_rating_fill_honors_the_configured_batch_limit(monkeypatch) -> None:
    observed: list[tuple[bool, int]] = []

    monkeypatch.setattr(
        stages,
        "get_settings",
        lambda: SimpleNamespace(
            DATA_FILL_RATING_BATCH_SIZE=48,
            DATA_FILL_INTER_GAME_DELAY=0,
        ),
    )
    monkeypatch.setattr(
        stages,
        "_rating_refresh_candidates",
        lambda force, limit: observed.append((force, limit)) or [],
    )

    result = asyncio.run(stages.fill_ratings(force=False))

    assert observed == [(False, 48)]
    assert result == {"refreshed": 0, "skipped": 0, "failed": 0}
