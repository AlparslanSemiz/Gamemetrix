import pytest
from fastapi import HTTPException

from app.account_security import hash_password, hash_secret, normalize_email, password_needs_rehash, verify_password
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
