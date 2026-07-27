"""
Provider quota guards.

OpenCritic's free RapidAPI plan has hard daily request/search ceilings and a
separate paid bandwidth overage. These tests pin local caps below those hard
ceilings and prevent retries from multiplying quota burn.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.config import METERED_SOURCES, OPENCRITIC_SEARCH_SOURCE, get_settings
from app.integrations.http_retry import request_with_retry
from app.integrations.rate_limiter import RateLimiter, WindowSpec
from app.services.data_fill.stages import RATING_BUDGET_SOURCES, catalog_import_target
from app.services import primary_score_backfill as primary_scores


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_throttled_response_is_not_retried() -> None:
    """A 429 must cost exactly one request — retrying multiplies quota burn."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "1"})

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/quota")

    assert response.status_code == 429
    assert attempts == 1


@pytest.mark.asyncio
async def test_server_error_is_retried() -> None:
    """Transient 5xx still retries — those do not indicate a quota problem."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        response = await request_with_retry(client, "GET", "https://example.test/flaky")

    assert response.status_code == 200
    assert attempts == 2


def test_opencritic_hard_limit_headroom_is_built_into_its_local_caps() -> None:
    cfg = get_settings()
    ordinary = cfg.budget_reserve_percent("RAWG")

    assert cfg.budget_reserve_percent("OpenCritic") == 0
    assert cfg.budget_reserve_percent(OPENCRITIC_SEARCH_SOURCE) == 0
    assert ordinary > 0, "every provider needs headroom below its ceiling"
    assert "OpenCritic" in METERED_SOURCES
    assert OPENCRITIC_SEARCH_SOURCE in METERED_SOURCES


def test_opencritic_search_has_its_own_tighter_bucket() -> None:
    limits = get_settings().provider_daily_limits()

    assert limits[OPENCRITIC_SEARCH_SOURCE] < limits["OpenCritic"], (
        "the search endpoint is rate-limited far more tightly than other routes"
    )


def test_opencritic_defaults_stay_within_the_free_usage_policy() -> None:
    cfg = get_settings()
    limits = cfg.provider_daily_limits()
    windows = cfg.provider_window_limits()

    assert limits["OpenCritic"] == 190
    assert limits[OPENCRITIC_SEARCH_SOURCE] == 24
    assert ("rolling", 3, 1) in windows["OpenCritic"]


def test_metacritic_shares_the_rawg_budget() -> None:
    """Both are fetched with the same RAWG key, so one budget must cover both."""
    assert get_settings().provider_budget_aliases()["Metacritic"] == "RAWG"


def test_monthly_rawg_window_stays_under_the_free_tier() -> None:
    cfg = get_settings()
    monthly = dict(
        (kind, limit) for kind, limit, _ in cfg.provider_window_limits()["RAWG"]
    )["monthly"]
    reserve = cfg.budget_reserve_percent("RAWG")
    usable_monthly = monthly * (100 - reserve) // 100
    usable_daily = cfg.provider_daily_limits()["RAWG"] * (100 - reserve) // 100

    assert usable_daily * 31 <= monthly, "31 full days must not exceed the monthly ceiling"
    assert usable_monthly < monthly


def test_non_rating_steamspy_budget_cannot_keep_rating_fill_alive() -> None:
    assert "SteamSpy" not in RATING_BUDGET_SOURCES


def test_rawg_monthly_window_uses_the_account_renewal_day() -> None:
    spec = WindowSpec(
        kind="monthly",
        seconds=31 * 24 * 60 * 60,
        limit=20_000,
        anchor_day=25,
    )

    assert RateLimiter._window_start(
        spec, datetime(2026, 7, 24, 23, 59, tzinfo=UTC)
    ) == datetime(2026, 6, 25, tzinfo=UTC)
    assert RateLimiter._window_start(
        spec, datetime(2026, 7, 25, tzinfo=UTC)
    ) == datetime(2026, 7, 25, tzinfo=UTC)


def test_ordered_data_fill_owns_the_first_provider_budget_after_boot() -> None:
    cfg = get_settings()

    assert cfg.STARTUP_RATING_REFRESH_LIMIT == 0
    assert cfg.STARTUP_METADATA_BACKFILL_LIMIT == 0
    assert cfg.SUMMARY_SHORTEN_STARTUP_LIMIT == 0


def test_groq_free_tier_has_one_shared_persistent_budget() -> None:
    cfg = get_settings()

    # Tokens, not requests, are what the free tier actually runs out of.
    assert 0 < cfg.provider_daily_token_limits()["Groq"] <= 200_000
    assert 0 < cfg.provider_daily_limits()["Groq"] <= 1_000
    assert cfg.budget_reserve_percent("Groq") > 0
    # 5 calls/min at our prompt sizes stays under the 8,000 TPM ceiling.
    assert cfg.GROQ_MIN_REQUEST_INTERVAL_SECONDS >= 12


class _Budget:
    """Stand-in for one api_request_budgets row."""

    def __init__(self, token_limit: int, token_count: int = 0) -> None:
        self.request_count = 0
        self.daily_limit = 1_000
        self.token_limit = token_limit
        self.token_count = token_count
        self.updated_at = datetime.now(UTC)


def _token_limiter(row: _Budget) -> RateLimiter:
    """Limiter whose every database touchpoint is stubbed.

    The session object is still the real one, but it is opened and committed
    without a single query, so it never connects.
    """
    limiter = RateLimiter()
    limiter._get_or_create_daily = lambda _db, _source: row  # type: ignore[method-assign]
    limiter._get_window_rows = lambda _db, _source: []  # type: ignore[method-assign]
    limiter._lock_database_budget = lambda _db, _source: None  # type: ignore[method-assign]
    return limiter


@pytest.mark.asyncio
async def test_a_token_budget_refuses_a_call_that_would_overshoot_it() -> None:
    row = _Budget(token_limit=10_000, token_count=8_400)
    limiter = _token_limiter(row)

    # 15% reserve leaves 8,500 usable: a 100-token call fits, a 2,000 one does not.
    assert await limiter.acquire("Groq", estimated_tokens=2_000) is False
    assert row.token_count == 8_400
    assert row.request_count == 0

    assert await limiter.acquire("Groq", estimated_tokens=100) is True
    assert row.token_count == 8_500
    assert row.request_count == 1


def test_settling_tokens_replaces_the_reservation_with_real_usage() -> None:
    row = _Budget(token_limit=10_000, token_count=1_600)
    limiter = _token_limiter(row)

    limiter.settle_tokens("Groq", reserved=1_600, actual=420)

    assert row.token_count == 420


def test_a_source_without_a_token_limit_is_unaffected() -> None:
    row = _Budget(token_limit=0)
    limiter = _token_limiter(row)

    assert asyncio.run(limiter.acquire("RAWG", estimated_tokens=999_999)) is True
    assert row.request_count == 1


def test_primary_score_catalog_scans_stream_plain_columns() -> None:
    class RecordingDb:
        selected = []

        def execute(self, statement):
            self.selected = [column["expr"] for column in statement.column_descriptions]
            return [
                (
                    7,
                    ["PC"],
                    [{"source": "Steam", "status": "live", "score": 90}],
                    88.0,
                )
            ]

    db = RecordingDb()
    candidates = primary_scores.primary_score_backfill_candidates(db, 10)

    assert db.selected == [
        primary_scores.Game.id,
        primary_scores.Game.platforms,
        primary_scores.Game.source_scores,
        primary_scores.Game.rank_score,
    ]
    assert primary_scores._SCAN_CHUNK <= 500
    assert candidates == [
        (7, ("OpenCritic", "Metacritic", "IGDB")),
    ]


def test_primary_score_candidates_finish_top_games_closest_to_four_scores_first() -> None:
    class RecordingDb:
        def execute(self, _statement):
            return [
                (
                    1,
                    ["PC"],
                    [{"source": "Steam", "status": "live", "score": 90}],
                    99.0,
                ),
                (
                    2,
                    ["PC"],
                    [
                        {"source": "Steam", "status": "live", "score": 90},
                        {"source": "IGDB", "status": "live", "score": 85},
                        {"source": "Metacritic", "status": "live", "score": 88},
                    ],
                    95.0,
                ),
            ]

    assert primary_scores.primary_score_backfill_candidates(RecordingDb(), 2) == [
        (2, ("OpenCritic",)),
        (1, ("OpenCritic", "Metacritic", "IGDB")),
    ]


def test_opencritic_without_an_id_stops_when_its_search_bucket_is_empty() -> None:
    class Limiter:
        def remaining(self, source: str) -> int:
            return 0 if source == OPENCRITIC_SEARCH_SOURCE else 100

    limiter = Limiter()

    assert primary_scores._source_budget_available(
        limiter,
        "OpenCritic",
        uses_local_metacritic=False,
        has_opencritic_id=False,
    ) is False
    assert primary_scores._source_budget_available(
        limiter,
        "OpenCritic",
        uses_local_metacritic=False,
        has_opencritic_id=True,
    ) is True


def test_primary_score_target_distinguishes_four_scores_from_platform_applicability() -> None:
    three_sources = [
        {"source": "OpenCritic", "status": "live", "score": 80},
        {"source": "Metacritic", "status": "live", "score": 81},
        {"source": "IGDB", "status": "live", "score": 82},
    ]
    coverage = primary_scores._coverage_for_rows(
        [
            (["PlayStation 5"], three_sources),
            (["PC"], [*three_sources, {"source": "Steam", "status": "live", "score": 83}]),
        ]
    )

    assert coverage["complete_games"] == 2
    assert coverage["four_score_games"] == 1
    assert coverage["non_pc_games"] == 1
    assert coverage["score_count_distribution"] == {
        "0": 0,
        "1": 0,
        "2": 0,
        "3": 1,
        "4": 1,
    }


def test_all_catalog_sources_stop_after_the_combined_target_is_met() -> None:
    assert catalog_import_target(
        source="Steam",
        cap=500,
        current_total=50_071,
        target_total=50_000,
    ) == 0
    assert catalog_import_target(
        source="IGDB",
        cap=5_000,
        current_total=50_071,
        target_total=50_000,
    ) == 0
    assert catalog_import_target(
        source="RAWG",
        cap=500,
        current_total=50_071,
        target_total=50_000,
    ) == 0
