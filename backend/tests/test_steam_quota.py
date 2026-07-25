import httpx

from app.integrations.steam_quota import stop_steam_requests_if_rate_limited


class _Limiter:
    def __init__(self) -> None:
        self.blocks: list[tuple[str, int]] = []

    def block(self, source: str, seconds: int) -> None:
        self.blocks.append((source, seconds))


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://store.steampowered.com/api/appdetails"),
    )


def test_steam_429_stops_more_requests(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.steam_quota.get_rate_limiter",
        lambda: limiter,
    )

    assert stop_steam_requests_if_rate_limited(_response(429)) is True
    assert limiter.blocks == [("Steam", 3600)]


def test_steam_non_rate_limit_error_does_not_trip_circuit(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.steam_quota.get_rate_limiter",
        lambda: limiter,
    )

    assert stop_steam_requests_if_rate_limited(_response(500)) is False
    assert limiter.blocks == []


def test_steam_429_honors_numeric_retry_after(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.steam_quota.get_rate_limiter",
        lambda: limiter,
    )
    response = _response(429)
    response.headers["Retry-After"] = "120"

    assert stop_steam_requests_if_rate_limited(response) is True
    assert limiter.blocks == [("Steam", 120)]
