"""Account hardening: per-account login limit, IPv6 rate-limit keys, mail after the response."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.rate_limit import get_client_ip
from app.services import login_throttle
from tests.test_tur2_catalog_limits import needs_postgres, pg_client  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_throttle():
    login_throttle.reset()
    yield
    login_throttle.reset()


def _fail(email, client, times, start=0.0):
    for n in range(times):
        login_throttle.reserve_login_attempt(email, client, now=start + n)


def test_pair_limit_blocks_only_the_attacking_client() -> None:
    _fail("v@example.com", "6.6.6.6", login_throttle.MAX_PAIR_ATTEMPTS)
    with pytest.raises(HTTPException) as blocked:
        login_throttle.reserve_login_attempt("v@example.com", "6.6.6.6", now=20.0)
    assert blocked.value.status_code == 429 and int(blocked.value.headers["Retry-After"]) > 800
    login_throttle.reserve_login_attempt("v@example.com", "1.2.3.4", now=20.0)  # the owner
    login_throttle.reserve_login_attempt("v@example.com", "6.6.6.6", now=20.0 + login_throttle.WINDOW_SECONDS)
    # A valid device cookie always passes.
    assert login_throttle.reserve_login_attempt("v@example.com", "6.6.6.6", device_trusted=True) == (None, 0.0)


def test_success_releases_the_reservation() -> None:
    for _ in range(30):
        token, _delay = login_throttle.reserve_login_attempt("a@example.com", "1.1.1.1", now=1.0)
        login_throttle.release_login_attempt("a@example.com", "1.1.1.1", token)
    assert login_throttle._pairs == {} and login_throttle._emails == {}


def test_email_limit_delays_with_backoff_and_never_refuses() -> None:
    email = "soft@example.com"
    for n in range(login_throttle.MAX_EMAIL_ATTEMPTS):  # distributed guessing, many addresses
        _token, delay = login_throttle.reserve_login_attempt(email, f"10.0.0.{n}", now=1.0 + n)
        assert delay == 0
    delays = [
        login_throttle.reserve_login_attempt(email, f"11.0.0.{n}", now=100.0 + n)[1] for n in range(7)
    ]
    assert delays == [1.0, 2.0, 4.0, 8.0, 15.0, 15.0, 15.0]
    # A device-cookie holder is not delayed at all.
    assert login_throttle.reserve_login_attempt(email, "9.9.9.9", device_trusted=True, now=101.0) == (None, 0.0)
    # The window passing resets the delay.
    assert login_throttle.reserve_login_attempt(email, "8.8.8.8", now=100.0 + login_throttle.WINDOW_SECONDS + 60)[1] == 0


def test_concurrent_attempts_cannot_exceed_the_limit() -> None:
    import threading

    passed: list[int] = []

    def attempt() -> None:
        try:
            login_throttle.reserve_login_attempt("race@example.com", "5.5.5.5", now=1.0)
            passed.append(1)
        except HTTPException:
            pass

    threads = [threading.Thread(target=attempt) for _ in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(passed) == login_throttle.MAX_PAIR_ATTEMPTS


def test_full_map_neither_refuses_new_keys_nor_evicts_live_counters(monkeypatch) -> None:
    monkeypatch.setattr(login_throttle, "MAX_TRACKED_KEYS", 6)
    _fail("victim@example.com", "6.6.6.6", login_throttle.MAX_PAIR_ATTEMPTS)
    for n in range(2):
        login_throttle.reserve_login_attempt(f"filler{n}@example.com", "2.2.2.2", now=5.0)
    # Full of live entries: a flood of new keys is let through untracked, never refused.
    for n in range(500):
        token, delay = login_throttle.reserve_login_attempt(f"new{n}@example.com", "3.3.3.3", now=6.0)
        assert token is None and delay == 0
    assert len(login_throttle._pairs) + len(login_throttle._emails) == 6
    with pytest.raises(HTTPException):  # the victim's attacker is still blocked
        login_throttle.reserve_login_attempt("victim@example.com", "6.6.6.6", now=7.0)
    token, _ = login_throttle.reserve_login_attempt(
        "late@example.com", "4.4.4.4", now=7.0 + login_throttle.WINDOW_SECONDS
    )
    assert token is not None  # expired entries were what made room


def test_device_cookie_is_signed_per_email_and_prefixed_in_production(monkeypatch) -> None:
    from fastapi import Response

    from app import account_security as sec

    response = Response()
    sec.set_device_cookie(response, "me@example.com")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("gm_device=") and "HttpOnly" in cookie
    value = cookie.split(";")[0].split("=", 1)[1]

    def request_with(name: str, val: str) -> Request:
        return Request({"type": "http", "method": "POST", "path": "/", "client": ("1.1.1.1", 1),
                        "headers": [(b"cookie", f"{name}={val}".encode())]})

    assert sec.device_cookie_valid(request_with("gm_device", value), "me@example.com")
    assert not sec.device_cookie_valid(request_with("gm_device", value), "other@example.com")
    assert not sec.device_cookie_valid(request_with("gm_device", "0" * 64), "me@example.com")
    assert not sec.device_cookie_valid(request_with("gm_device", ""), "me@example.com")

    monkeypatch.setattr(sec, "get_settings", lambda: type("S", (), {"is_production": True, "JWT_SECRET_KEY": "x" * 40})())
    assert sec.device_cookie_name() == "__Host-gm_device"
    prod = Response()
    sec.set_device_cookie(prod, "me@example.com")
    assert "Secure" in prod.headers["set-cookie"] and prod.headers["set-cookie"].startswith("__Host-gm_device=")


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
    login_throttle.reset()
    origin = {"Origin": "http://localhost:5173"}
    body = {"email": "grind@example.com", "password": "wrong password value"}
    codes = [client.post("/api/account/login", headers=origin, json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    login_throttle.reset()

