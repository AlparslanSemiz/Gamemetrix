import pytest

from app.integrations import sync as sync_module
from app.integrations.sync import SOURCE_WEIGHTS, calculate_metrix_score
from app.integrations.types import ExternalScore
from app.models import Game
from app.services.primary_score_backfill import missing_primary_score_sources


def _score(source: str, score: float, reviews: int = 500) -> dict[str, object]:
    return {
        "source": source,
        "score": score,
        "scale": 100,
        "status": "live",
        "review_count": reviews,
    }


def test_rawg_never_substitutes_for_a_primary_score() -> None:
    assert calculate_metrix_score([_score("RAWG", 99)]) == 0

    primary = [_score("Metacritic", 80)]
    assert calculate_metrix_score(primary + [_score("RAWG", 10)]) == calculate_metrix_score(primary)


def test_rawg_only_does_not_raise_rating_confidence() -> None:
    game = Game(
        title="Supplementary only",
        slug="supplementary-only",
        platforms=["PC"],
        source_scores=[_score("RAWG", 90, 50_000)],
        content_type="game",
    )
    assert game.live_primary_source_count == 0
    assert game.confidence_level == "Catalog"


def test_primary_score_completion_only_targets_applicable_sources() -> None:
    console_game = Game(
        title="Console only",
        slug="console-only",
        platforms=["Nintendo Switch"],
        source_scores=[],
        content_type="game",
    )
    pc_game = Game(
        title="PC game",
        slug="pc-game",
        platforms=["PC"],
        source_scores=[],
        content_type="game",
    )

    assert missing_primary_score_sources(console_game) == ("OpenCritic", "Metacritic", "IGDB")
    assert missing_primary_score_sources(pc_game) == ("OpenCritic", "Metacritic", "IGDB", "Steam")


def test_runtime_primary_weights_change_the_composite_score() -> None:
    original = dict(SOURCE_WEIGHTS)
    scores = [
        _score("Metacritic", 100),
        _score("OpenCritic", 50),
        _score("Steam", 50),
        _score("IGDB", 50),
    ]
    try:
        SOURCE_WEIGHTS.update({"Metacritic": 1.0, "OpenCritic": 0.0, "Steam": 0.0, "IGDB": 0.0})
        critic_weighted = calculate_metrix_score(scores)
        SOURCE_WEIGHTS.update({"Metacritic": 0.0, "OpenCritic": 0.0, "Steam": 1.0, "IGDB": 0.0})
        steam_weighted = calculate_metrix_score(scores)
        assert critic_weighted > steam_weighted
    finally:
        SOURCE_WEIGHTS.clear()
        SOURCE_WEIGHTS.update(original)


def test_invalid_provider_scores_do_not_enter_the_composite() -> None:
    malformed = [
        _score("Metacritic", 101),
        _score("OpenCritic", float("nan")),
        {"source": "Steam", "score": "not-a-number", "status": "live", "review_count": -1},
    ]
    assert calculate_metrix_score(malformed) == 0


def test_external_score_rejects_invalid_provider_values() -> None:
    with pytest.raises(ValueError):
        ExternalScore(source="Steam", score=101)
    with pytest.raises(ValueError):
        ExternalScore(source="Steam", score=float("nan"))
    with pytest.raises(ValueError):
        ExternalScore(source="Steam", score=80, review_count=-1)


@pytest.mark.asyncio
async def test_cached_database_score_does_not_consume_provider_budget(monkeypatch) -> None:
    class FakeLimiter:
        acquire_calls = 0

        def remaining(self, _source: str) -> int:
            raise AssertionError("No budget lookup should occur for a database-backed score")

        async def acquire(self, _source: str) -> bool:
            self.acquire_calls += 1
            return True

    limiter = FakeLimiter()
    monkeypatch.setattr(sync_module, "get_rate_limiter", lambda: limiter)

    async def fetch() -> ExternalScore:
        return ExternalScore(source="Metacritic", score=88, review_count=40)

    result = await sync_module._resolve_score(
        "Metacritic",
        None,
        fetch,
        budget_source=None,
    )

    assert result.score == 88
    assert limiter.acquire_calls == 0


@pytest.mark.asyncio
async def test_provider_exception_details_never_expose_request_secrets() -> None:
    async def fetch() -> ExternalScore:
        raise RuntimeError("https://api.rawg.io/games?key=super-secret")

    result = await sync_module._resolve_score(
        "Metacritic",
        None,
        fetch,
        budget_source=None,
    )

    assert result.status == "unavailable"
    assert result.detail == "Metacritic request failed (RuntimeError)."
    assert "super-secret" not in result.detail
