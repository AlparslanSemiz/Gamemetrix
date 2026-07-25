"""
Provider quota guards.

OpenCritic is a metered plan: exceeding it is billed. These tests pin the two
behaviours that keep real usage below the provider ceiling — a throttled request
is never retried, and every ceiling is reduced by a safety reserve.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.config import METERED_SOURCES, OPENCRITIC_SEARCH_SOURCE, get_settings
from app.integrations.http_retry import request_with_retry
from app.integrations.rate_limiter import RateLimiter, WindowSpec
from app.services.data_fill.stages import RATING_BUDGET_SOURCES


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


def test_metered_sources_reserve_more_headroom() -> None:
    cfg = get_settings()
    metered = cfg.budget_reserve_percent("OpenCritic")
    ordinary = cfg.budget_reserve_percent("RAWG")

    assert metered >= ordinary
    assert ordinary > 0, "every provider needs headroom below its ceiling"
    assert "OpenCritic" in METERED_SOURCES
    assert OPENCRITIC_SEARCH_SOURCE in METERED_SOURCES


def test_opencritic_search_has_its_own_tighter_bucket() -> None:
    limits = get_settings().provider_daily_limits()

    assert limits[OPENCRITIC_SEARCH_SOURCE] < limits["OpenCritic"], (
        "the search endpoint is rate-limited far more tightly than other routes"
    )


def test_opencritic_defaults_stay_within_the_free_usage_policy() -> None:
    limits = get_settings().provider_daily_limits()

    assert limits["OpenCritic"] == 4
    assert limits[OPENCRITIC_SEARCH_SOURCE] == 2


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
