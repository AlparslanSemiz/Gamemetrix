import httpx

from app.integrations.rawg_quota import stop_rawg_requests_if_quota_exhausted


class _Limiter:
    def __init__(self) -> None:
        self.limits: list[tuple[str, int]] = []

    def set_limit(self, source: str, value: int) -> None:
        self.limits.append((source, value))


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "https://api.rawg.io/api/games"),
    )


def test_monthly_limit_401_stops_more_rawg_requests(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.rawg_quota.get_rate_limiter",
        lambda: limiter,
    )

    exhausted = stop_rawg_requests_if_quota_exhausted(
        _response(401, {"error": "The monthly API limit reached"})
    )

    assert exhausted is True
    assert limiter.limits == [("RAWG", 0)]


def test_invalid_key_401_is_not_misclassified_as_quota(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.rawg_quota.get_rate_limiter",
        lambda: limiter,
    )

    exhausted = stop_rawg_requests_if_quota_exhausted(
        _response(401, {"error": "Invalid API key"})
    )

    assert exhausted is False
    assert limiter.limits == []
