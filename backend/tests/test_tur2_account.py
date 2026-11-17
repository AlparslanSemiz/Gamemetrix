"""Account hardening: per-account login limit, IPv6 rate-limit keys, mail after the response."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.rate_limit import get_client_ip
from app.services import login_throttle
from tests.test_tur2_catalog_limits import needs_postgres, pg_client  # noqa: F401


def test_login_throttle_blocks_after_ten_failures_and_recovers() -> None:
    login_throttle._failures.clear()
    email = "victim@example.com"
    for second in range(10):
        login_throttle.ensure_login_allowed(email, now=float(second))
        login_throttle.record_login_failure(email, now=float(second))
    with pytest.raises(HTTPException) as blocked:
        login_throttle.ensure_login_allowed(email, now=20.0)
    assert blocked.value.status_code == 429
    assert int(blocked.value.headers["Retry-After"]) > 800
    login_throttle.ensure_login_allowed("other@example.com", now=20.0)
    login_throttle.ensure_login_allowed(email, now=20.0 + login_throttle.WINDOW_SECONDS)


def test_login_throttle_success_clears_failures() -> None:
    login_throttle._failures.clear()
    for _ in range(9):
        login_throttle.record_login_failure("a@example.com")
    login_throttle.clear_login_failures("a@example.com")
    for _ in range(9):
        login_throttle.record_login_failure("a@example.com")
    login_throttle.ensure_login_allowed("a@example.com")


def _request(peer: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": (peer, 1)})


def test_ipv6_clients_share_one_bucket_per_slash_64() -> None:
    a = get_client_ip(_request("2001:db8:1:2:aaaa:bbbb:cccc:dddd"))
    b = get_client_ip(_request("2001:db8:1:2:1111:2222:3333:4444"))
    other = get_client_ip(_request("2001:db8:1:3::1"))
    assert a == b == "2001:db8:1:2::/64"
    assert other != a
    assert get_client_ip(_request("203.0.113.7")) == "203.0.113.7"
    assert get_client_ip(_request("::ffff:203.0.113.7")) == "203.0.113.7"


@needs_postgres
def test_forgot_and_register_send_mail_after_the_response(pg_client, monkeypatch) -> None:
    from datetime import UTC, datetime

    from app.models import User
    from app.routers.account import auth as account_auth
    from app.services import account_tokens

    client, sessions = pg_client
    events: list[str] = []

    async def fake_send(_to, subject, _body):
        events.append(subject)

    monkeypatch.setattr(account_tokens, "send_account_email", fake_send)
    origin = {"Origin": "http://localhost:5173"}

    registered = client.post(
        "/api/account/register", headers=origin,
        json={"display_name": "Test User", "email": "bg@example.com", "password": "correct horse battery staple"},
    )
    assert registered.status_code == 202
    assert events == ["Verify your GameMetrix account"]

    # A second registration for the same pending address answers identically.
    again = client.post(
        "/api/account/register", headers=origin,
        json={"display_name": "Test User", "email": "bg@example.com", "password": "another long passphrase here"},
    )
    assert again.status_code == 202 and again.json() == registered.json()

    with sessions() as db:
        user = db.query(User).filter_by(email="bg@example.com").one()
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    events.clear()
    for email in ("bg@example.com", "nobody@example.com"):
        forgot = client.post("/api/account/password/forgot", headers=origin, json={"email": email})
        assert forgot.status_code == 202
    assert events == ["Reset your GameMetrix password"]
    assert account_auth._send_password_reset_in_background  # exported for the router


@needs_postgres
def test_login_is_locked_per_account_after_repeated_failures(pg_client) -> None:
    client, _sessions = pg_client
    login_throttle._failures.clear()
    origin = {"Origin": "http://localhost:5173"}
    body = {"email": "grind@example.com", "password": "wrong password value"}
    codes = [client.post("/api/account/login", headers=origin, json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    login_throttle._failures.clear()

