"""Admin passwords longer than bcrypt's 72-byte window keep working on bcrypt >= 5."""

import bcrypt

from app import security


def test_long_admin_password_verifies_against_a_truncating_hash(monkeypatch) -> None:
    long_password = "x" * 60 + "ğ" * 20  # 100 UTF-8 bytes
    stored = bcrypt.hashpw(long_password.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)).decode()
    settings = security.get_settings()
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin", raising=False)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", stored, raising=False)
    assert security.verify_admin_password("admin", long_password) is True
    assert security.verify_admin_password("admin", "x" * 60) is False
