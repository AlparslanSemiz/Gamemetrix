from types import SimpleNamespace

import httpx
import pytest

from app.integrations import itad_service as itad_module
from app.integrations.itad_service import DEFAULT_ITAD_COUNTRY, ITADService


class _Limiter:
    async def acquire(self, _source: str) -> bool:
        return True


class _Client:
    def __init__(self, responses: dict[str, object], calls: list[dict[str, object]]):
        self.responses = responses
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        path = httpx.URL(url).path
        return httpx.Response(
            200,
            json=self.responses[path],
            request=httpx.Request("POST", url),
        )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        path = httpx.URL(url).path
        return httpx.Response(
            200,
            json=self.responses[path],
            request=httpx.Request("GET", url),
        )


def _configure_itad(monkeypatch: pytest.MonkeyPatch, responses: dict[str, object]) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    settings = SimpleNamespace(ITAD_API_KEY="test-key", itad_configured=lambda: True)
    monkeypatch.setattr(itad_module, "get_settings", lambda: settings)
    monkeypatch.setattr(itad_module, "get_rate_limiter", lambda: _Limiter())
    monkeypatch.setattr(
        itad_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(responses, calls),
    )
    return calls


@pytest.mark.asyncio
async def test_itad_batch_endpoints_follow_the_current_post_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    itad_id = "018d937f-012f-73b8-ab2c-898516969e6a"
    calls: list[dict[str, object]] = []
    responses = {
        "/games/prices/v3": [{"id": itad_id, "deals": [{"cut": 50}]}],
        "/games/historylow/v1": [{"id": itad_id, "low": {"price": {"amount": 1.0}}}],
        "/games/subs/v1": [{"id": itad_id, "subs": [{"name": "Game Pass"}]}],
    }
    settings = SimpleNamespace(
        ITAD_API_KEY="test-key",
        itad_configured=lambda: True,
    )
    monkeypatch.setattr(itad_module, "get_settings", lambda: settings)
    monkeypatch.setattr(itad_module, "get_rate_limiter", lambda: _Limiter())
    monkeypatch.setattr(
        itad_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(responses, calls),
    )

    service = ITADService()
    assert await service.get_prices(itad_id) == [{"cut": 50}]
    assert await service.get_history_low(itad_id) == {"price": {"amount": 1.0}}
    assert await service.get_subscriptions(itad_id) == ["Game Pass"]

    assert [call["url"] for call in calls] == [
        f"{itad_module.ITAD_BASE}/games/prices/v3",
        f"{itad_module.ITAD_BASE}/games/historylow/v1",
        f"{itad_module.ITAD_BASE}/games/subs/v1",
    ]
    assert all(call["json"] == [itad_id] for call in calls)
    assert all(call["params"]["country"] == DEFAULT_ITAD_COUNTRY for call in calls[:2])
    assert calls[2].get("params") is None


def test_itad_default_country_is_an_iso_country_code() -> None:
    assert DEFAULT_ITAD_COUNTRY == "DE"


@pytest.mark.asyncio
async def test_lookup_rejects_a_title_that_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ITAD's lookup is fuzzy; an unverified hit would store another game's price."""
    _configure_itad(
        monkeypatch,
        {"/games/lookup/v1": {"found": True, "game": {"id": "abc", "title": "Portal 2"}}},
    )
    service = ITADService()

    assert await service.lookup_id("Portal 2") == "abc"
    assert await service.lookup_id("Half-Life 2") is None


@pytest.mark.asyncio
async def test_price_data_carries_the_store_deal_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the URL the panel renders a dead row for non-searchable stores."""
    itad_id = "018d937f-012f-73b8-ab2c-898516969e6a"
    deal_url = "https://www.fanatical.com/en/game/hades"
    _configure_itad(
        monkeypatch,
        {
            "/games/lookup/v1": {"found": True, "game": {"id": itad_id, "title": "Hades"}},
            "/games/prices/v3": [
                {
                    "id": itad_id,
                    "deals": [
                        {
                            "shop": {"name": "Fanatical"},
                            "price": {"amount": 9.99, "currency": "EUR"},
                            "regular": {"amount": 19.99},
                            "cut": 50,
                            "url": deal_url,
                        }
                    ],
                }
            ],
            "/games/historylow/v1": [{"id": itad_id, "low": {"price": {"amount": 4.99}}}],
            "/games/subs/v1": [{"id": itad_id, "subs": []}],
        },
    )

    price_data = await ITADService().fetch_price_data("Hades")

    assert price_data is not None
    assert price_data.url == deal_url
    assert price_data.store == "Fanatical"


def test_over_long_deal_urls_are_dropped_rather_than_truncated() -> None:
    """A truncated URL is a broken link, and ITAD forbids altering supplied URLs."""
    assert itad_module._deal_url("https://store.example/" + "x" * 600) is None
    assert itad_module._deal_url("https://store.example/game") == "https://store.example/game"
    assert itad_module._deal_url(None) is None
