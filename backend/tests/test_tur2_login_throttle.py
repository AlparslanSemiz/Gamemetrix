"""Postgres-backed login throttle and trusted devices."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import account_security as sec
from app.models import LoginThrottle, TrustedDevice, User
from app.services import login_throttle as lt
from app.services import trusted_devices
from tests.test_tur2_catalog_limits import needs_postgres, pg_client  # noqa: F401

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
pytestmark = needs_postgres


def _reserve(sessions, email, client, *, now=T0, trusted=False):
    with sessions() as db:
        return lt.reserve_login_attempt(db, email, client, trusted_device=trusted, now=now)


def _blocked(sessions, email, client, **kw) -> HTTPException:
    with pytest.raises(HTTPException) as raised:
        _reserve(sessions, email, client, **kw)
    assert raised.value.status_code == 429
    return raised.value


def test_pair_limit_blocks_only_that_client(pg_client) -> None:
    _client, sessions = pg_client
    for n in range(lt.MAX_PAIR_ATTEMPTS):
        _reserve(sessions, "v@example.com", "6.6.6.6", now=T0 + timedelta(seconds=n))
    blocked = _blocked(sessions, "v@example.com", "6.6.6.6", now=T0 + timedelta(seconds=20))
    assert int(blocked.headers["Retry-After"]) > 800
    _reserve(sessions, "v@example.com", "1.2.3.4", now=T0 + timedelta(seconds=20))  # the owner
    _reserve(sessions, "v@example.com", "6.6.6.6", now=T0 + timedelta(seconds=lt.WINDOW_SECONDS + 5))


def test_rejected_attempts_are_not_counted(pg_client) -> None:
    _client, sessions = pg_client
    for _ in range(lt.MAX_PAIR_ATTEMPTS):
        _reserve(sessions, "c@example.com", "6.6.6.6")
    for _ in range(5):
        _blocked(sessions, "c@example.com", "6.6.6.6")
    with sessions() as db:
        assert db.get(LoginThrottle, "pair:c@example.com|6.6.6.6").failures == lt.MAX_PAIR_ATTEMPTS
        assert db.get(LoginThrottle, "email:c@example.com").failures == lt.MAX_PAIR_ATTEMPTS


def test_email_limit_sets_next_allowed_at_exponentially(pg_client) -> None:
    _client, sessions = pg_client
    email = "soft@example.com"
    for n in range(lt.MAX_EMAIL_ATTEMPTS):  # distributed guessing from many addresses
        _reserve(sessions, email, f"10.0.0.{n}", now=T0)
    now = T0
    waits = []
    for _ in range(9):
        _reserve(sessions, email, "11.0.0.1", now=now)  # accepted, pushes next_allowed_at out
        with sessions() as db:
            allowed = db.get(LoginThrottle, f"email:{email}").next_allowed_at
        waits.append(int((allowed - now).total_seconds()))
        early = _blocked(sessions, email, "12.0.0.1", now=now)  # arrives before it
        assert int(early.headers["Retry-After"]) >= 1
        now = allowed  # the wait has passed
    assert waits == [1, 2, 4, 8, 16, 32, 60, 60, 60]


def test_trusted_device_skips_email_gate_but_pair_limit_is_only_loosened(pg_client) -> None:
    _client, sessions = pg_client
    email = "t@example.com"
    for n in range(lt.MAX_EMAIL_ATTEMPTS + 1):  # the 21st sets next_allowed_at
        _reserve(sessions, email, f"10.0.0.{n}")
    _blocked(sessions, email, "9.9.9.9")  # untrusted, gated by next_allowed_at
    for _ in range(lt.TRUSTED_PAIR_ATTEMPTS):
        _reserve(sessions, email, "9.9.9.9", trusted=True)
    _blocked(sessions, email, "9.9.9.9", trusted=True)  # not a bypass


def test_release_hands_the_attempt_back(pg_client) -> None:
    _client, sessions = pg_client
    for _ in range(40):
        with sessions() as db:
            reservation = lt.reserve_login_attempt(db, "ok@example.com", "1.1.1.1", now=T0)
            lt.release_login_attempt(db, reservation)
    with sessions() as db:
        assert db.get(LoginThrottle, "pair:ok@example.com|1.1.1.1").failures == 0


def test_concurrent_requests_cannot_exceed_the_limits(pg_client) -> None:
    _client, sessions = pg_client
    passed: list[int] = []
    lock = threading.Lock()

    def attempt() -> None:
        try:
            _reserve(sessions, "race@example.com", "5.5.5.5")
            with lock:
                passed.append(1)
        except HTTPException:
            pass

    threads = [threading.Thread(target=attempt) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(passed) == lt.MAX_PAIR_ATTEMPTS

    # E-mail layer: past the limit, simultaneous requests cannot all get through the wait.
    passed.clear()

    def email_attempt(n: int) -> None:
        try:
            _reserve(sessions, "race2@example.com", f"7.7.{n // 200}.{n % 200}")
            with lock:
                passed.append(1)
        except HTTPException:
            pass

    threads = [threading.Thread(target=email_attempt, args=(n,)) for n in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert lt.MAX_EMAIL_ATTEMPTS <= len(passed) <= lt.MAX_EMAIL_ATTEMPTS + 1


def test_purge_removes_old_counters_and_expired_devices(pg_client) -> None:
    _client, sessions = pg_client
    _reserve(sessions, "old@example.com", "1.1.1.1", now=T0 - timedelta(hours=2))
    _reserve(sessions, "new@example.com", "1.1.1.1", now=T0)
    with sessions() as db:
        assert lt.purge_expired(db, now=T0) == 2
        assert len(db.scalars(select(LoginThrottle)).all()) == 2


def _user(db, email="dev@example.com") -> User:
    now = datetime.now(UTC)
    user = User(id="u-" + email, email=email, display_name="Dev User", password_hash=None,
                email_verified_at=now, is_active=True, created_at=now, updated_at=now)
    db.add(user)
    db.commit()
    return user


def test_device_tokens_are_random_hashed_and_user_bound(pg_client) -> None:
    _client, sessions = pg_client
    with sessions() as db:
        a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
        raw = trusted_devices.issue_device(db, a.id)
        assert len(raw) == 64 and raw != trusted_devices.issue_device(db, a.id)
        assert raw not in {d.token_hash for d in db.scalars(select(TrustedDevice)).all()}
        assert trusted_devices.is_trusted_device(db, a.id, raw)
        assert not trusted_devices.is_trusted_device(db, b.id, raw)
        assert not trusted_devices.is_trusted_device(db, a.id, "0" * 64)
        assert not trusted_devices.is_trusted_device(db, a.id, raw, now=datetime.now(UTC) + timedelta(days=31))


def test_session_revocation_and_password_reset_delete_devices(pg_client) -> None:
    client, sessions = pg_client
    from app.services.account_tokens import issue_token

    with sessions() as db:
        user = _user(db)
        raw = trusted_devices.issue_device(db, user.id)
        sec.revoke_user_sessions(db, user.id)
        db.commit()
        assert not trusted_devices.is_trusted_device(db, user.id, raw)

        raw = trusted_devices.issue_device(db, user.id)
        token = issue_token(db, user, "reset_password", 1)
    reset = client.post(
        "/api/account/password/reset",
        headers={"Origin": "http://localhost:5173"},
        json={"token": token, "password": "a brand new long passphrase"},
    )
    assert reset.status_code == 200
    with sessions() as db:
        assert not trusted_devices.is_trusted_device(db, "u-dev@example.com", raw)


def test_login_issues_a_device_cookie_that_is_recognized_afterwards(pg_client) -> None:
    client, sessions = pg_client
    origin = {"Origin": "http://localhost:5173"}
    password = "correct horse battery staple"
    with sessions() as db:
        user = _user(db, "login@example.com")
        user.password_hash = sec.hash_password(password)
        db.commit()
    body = {"email": "login@example.com", "password": password}

    first = client.post("/api/account/login", headers=origin, json=body)
    assert first.status_code == 200
    assert "gm_device" in first.cookies and "HttpOnly" in first.headers["set-cookie"]
    with sessions() as db:
        assert db.query(TrustedDevice).count() == 1
        assert db.get(LoginThrottle, "pair:login@example.com|testclient").failures == 0

    second = client.post("/api/account/login", headers=origin, json=body)  # same cookie jar
    assert second.status_code == 200
    with sessions() as db:
        assert db.query(TrustedDevice).count() == 1  # recognized, no second device issued


def test_device_cookie_is_host_prefixed_in_production(monkeypatch) -> None:
    from fastapi import Response

    monkeypatch.setattr(sec, "get_settings", lambda: type("S", (), {"is_production": True})())
    response = Response()
    sec.set_device_cookie(response, "tok")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-gm_device=tok") and "Secure" in cookie and "HttpOnly" in cookie
    assert "SameSite=lax" in cookie and "Path=/" in cookie
