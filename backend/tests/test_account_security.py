from app.account_security import hash_password, hash_secret, normalize_email, password_needs_rehash, verify_password
from app.routers.account import _safe_return_to


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
    assert _safe_return_to("/account?tab=alerts") == "/account?tab=alerts"
    assert _safe_return_to("https://evil.example/account") == "/account"
    assert _safe_return_to("//evil.example/account") == "/account"
    assert _safe_return_to("/\\evil.example/account") == "/account"
