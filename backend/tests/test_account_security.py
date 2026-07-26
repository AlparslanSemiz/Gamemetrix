import asyncio
import threading
import time

import pytest
from fastapi import HTTPException

import app.account_security as account_security
from app.account_security import (
    hash_password,
    hash_password_async,
    hash_secret,
    normalize_email,
    password_needs_rehash,
    verify_password,
)
from app.main import app
from app.routers.account.oauth import safe_return_to
from app.security import AuthenticatedUser, create_access_token, optional_admin_user


def test_passwords_use_argon2id_and_verify() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)
    assert not password_needs_rehash(encoded)


def test_secret_hashes_are_stable_without_exposing_input() -> None:
    hashed = hash_secret("session-token")
    assert len(hashed) == 64
    assert hashed == hash_secret("session-token")
    assert "session-token" not in hashed


def test_email_normalization_is_case_insensitive() -> None:
    assert normalize_email("  User.Name@Example.COM ") == "user.name@example.com"


def test_oauth_return_path_rejects_external_and_ambiguous_urls() -> None:
    assert safe_return_to("/account?tab=alerts") == "/account?tab=alerts"
    assert safe_return_to("https://evil.example/account") == "/account"
    assert safe_return_to("//evil.example/account") == "/account"
    assert safe_return_to("/\\evil.example/account") == "/account"


def test_optional_admin_identity_accepts_only_a_valid_admin_token() -> None:
    admin_token = create_access_token(AuthenticatedUser(username="admin", role="admin"))
    user_token = create_access_token(AuthenticatedUser(username="user", role="user"))

    assert optional_admin_user(None) is None
    assert optional_admin_user(admin_token) == AuthenticatedUser(username="admin", role="admin")
    assert optional_admin_user(user_token) is None
    with pytest.raises(HTTPException) as exc_info:
        optional_admin_user("not-a-jwt")
    assert exc_info.value.status_code == 401


def test_unsubscribe_is_post_only_and_does_not_accept_query_tokens() -> None:
    methods = set(app.openapi()["paths"]["/api/account/email/unsubscribe"])

    assert methods == {"post"}


@pytest.mark.asyncio
async def test_argon2_jobs_are_bounded_to_two_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = threading.Lock()
    active = 0
    maximum = 0

    def slow_hash(password: str) -> str:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return f"hash:{password}"

    monkeypatch.setattr(account_security, "hash_password", slow_hash)
    monkeypatch.setattr(account_security, "_PASSWORD_JOB_SLOTS", threading.BoundedSemaphore(2))

    results = await asyncio.gather(
        *(hash_password_async(f"password-{index}") for index in range(6))
    )

    assert results == [f"hash:password-{index}" for index in range(6)]
    assert maximum == 2


@pytest.mark.asyncio
async def test_argon2_saturation_returns_retryable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(account_security, "_PASSWORD_JOB_SLOTS", threading.BoundedSemaphore(0))
    monkeypatch.setattr(account_security, "_PASSWORD_JOB_WAIT_SECONDS", 0.01)

    with pytest.raises(HTTPException) as exc_info:
        await hash_password_async("a secure password")

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "1"}
