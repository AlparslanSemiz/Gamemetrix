import httpx

from app.integrations.steam_quota import stop_steam_requests_if_rate_limited


class _Limiter:
    def __init__(self) -> None:
        self.limits: list[tuple[str, int]] = []

    def set_limit(self, source: str, value: int) -> None:
        self.limits.append((source, value))


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
    assert limiter.limits == [("Steam", 0)]


def test_steam_non_rate_limit_error_does_not_trip_circuit(monkeypatch) -> None:
    limiter = _Limiter()
    monkeypatch.setattr(
        "app.integrations.steam_quota.get_rate_limiter",
        lambda: limiter,
    )

    assert stop_steam_requests_if_rate_limited(_response(500)) is False
    assert limiter.limits == []
