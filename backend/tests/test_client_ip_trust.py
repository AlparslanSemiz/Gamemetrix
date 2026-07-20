"""
Client-IP resolution must not be forgeable.

The rate limiter keys on this value, so a caller that can dictate it gets
unlimited attempts against the auth endpoints — and every audit/analytics row
written for that request carries an address of the attacker's choosing.
"""

from starlette.requests import Request

from app.rate_limit import get_client_ip
from app.routers.analytics import _client_ip


def _request(headers: dict[str, str], peer: str | None = "203.0.113.7") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 12345) if peer else None,
    }
    return Request(scope)


def test_rate_limit_key_ignores_forwarded_headers() -> None:
    spoofed = _request({
        "x-forwarded-for": "1.2.3.4",
        "x-real-ip": "5.6.7.8",
        "cf-connecting-ip": "9.10.11.12",
    })

    assert get_client_ip(spoofed) == "203.0.113.7"


def test_rate_limit_key_rotation_does_not_change_the_key() -> None:
    """Rotating a header must not yield a fresh bucket."""
    keys = {
        get_client_ip(_request({"x-forwarded-for": f"10.0.0.{octet}"}))
        for octet in range(1, 20)
    }

    assert keys == {"203.0.113.7"}


def test_rate_limit_key_falls_back_when_peer_is_unknown() -> None:
    assert get_client_ip(_request({}, peer=None)) == "unknown"


def test_analytics_ip_ignores_forwarded_headers() -> None:
    spoofed = _request({
        "x-real-ip": "1.2.3.4",
        "x-forwarded-for": "5.6.7.8",
        "cf-connecting-ip": "9.10.11.12",
    })

    assert _client_ip(spoofed) == "203.0.113.7"


def test_analytics_ip_rejects_a_malformed_peer() -> None:
    assert _client_ip(_request({}, peer="not-an-ip")) is None
