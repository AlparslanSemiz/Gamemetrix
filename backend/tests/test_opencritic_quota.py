from collections import Counter

import httpx
import pytest

from app.config import OPENCRITIC_SEARCH_SOURCE
from app.integrations import opencritic as score_adapter
from app.integrations import opencritic_service as service_adapter

_REAL_ASYNC_CLIENT = httpx.AsyncClient


class _Settings:
    OPENCRITIC_API_BASE = "https://opencritic-api.p.rapidapi.com"
    OPENCRITIC_API_KEY = ""
    RAPIDAPI_KEY = "test-key"
    RAPIDAPI_HOST = "opencritic-api.p.rapidapi.com"

    def opencritic_configured(self) -> bool:
        return True


class _Limiter:
    def __init__(self) -> None:
        self.acquired: Counter[str] = Counter()

    def remaining(self, _source: str) -> int:
        return 100

    async def acquire(self, source: str) -> bool:
        self.acquired[source] += 1
        return True


def _client_factory(handler):
    def factory(*_args, **_kwargs) -> httpx.AsyncClient:
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    return factory


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/game/search"):
        return httpx.Response(
            200,
            json=[
                {
                    "id": 110,
                    "name": "Portal 2",
                    "firstReleaseDate": "2011-04-19",
                }
            ],
        )
    return httpx.Response(
        200,
        json={
            "id": 110,
            "name": "Portal 2",
            "firstReleaseDate": "2011-04-19",
            "topCriticScore": 95,
            "numReviews": 40,
        },
    )


@pytest.mark.asyncio
async def test_opencritic_title_lookup_counts_search_and_both_total_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(score_adapter, "get_settings", lambda: _Settings())
    monkeypatch.setattr(score_adapter, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(score_adapter.httpx, "AsyncClient", _client_factory(_handler))

    score = await score_adapter.get_opencritic_score("Portal 2", release_year=2011)

    assert score.score == 95
    assert limiter.acquired["OpenCritic"] == 2
    assert limiter.acquired[OPENCRITIC_SEARCH_SOURCE] == 1


@pytest.mark.asyncio
async def test_opencritic_known_id_uses_only_one_total_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(score_adapter, "get_settings", lambda: _Settings())
    monkeypatch.setattr(score_adapter, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(score_adapter.httpx, "AsyncClient", _client_factory(_handler))

    score = await score_adapter.get_opencritic_score(
        "Portal 2",
        release_year=2011,
        opencritic_id=110,
    )

    assert score.score == 95
    assert limiter.acquired["OpenCritic"] == 1
    assert limiter.acquired[OPENCRITIC_SEARCH_SOURCE] == 0


@pytest.mark.asyncio
async def test_opencritic_source_test_accounts_for_search_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(service_adapter, "get_settings", lambda: _Settings())
    monkeypatch.setattr(service_adapter, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(service_adapter.httpx, "AsyncClient", _client_factory(_handler))

    game = await service_adapter.opencritic_service.search_game("Portal 2", 2011)

    assert game is not None
    assert game.score == 95
    assert limiter.acquired["OpenCritic"] == 2
    assert limiter.acquired[OPENCRITIC_SEARCH_SOURCE] == 1


@pytest.mark.asyncio
async def test_opencritic_dashboard_health_does_not_burn_search_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(service_adapter, "get_settings", lambda: _Settings())
    monkeypatch.setattr(service_adapter, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(service_adapter.httpx, "AsyncClient", _client_factory(_handler))

    health = await service_adapter.opencritic_service.health_check()

    assert health.working is True
    assert health.status == "ok"
    assert limiter.acquired == Counter()
