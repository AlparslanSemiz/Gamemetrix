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
