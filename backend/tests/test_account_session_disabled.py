"""GET /api/account/session answers 200 even when accounts are switched off."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture()
def client():
    test_client = TestClient(app)
    yield test_client
    test_client.close()


def test_session_reports_accounts_disabled_instead_of_503(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ACCOUNT_AUTH_ENABLED", False)

    response = client.get("/api/account/session")

    assert response.status_code == 200
    assert response.json() == {"account": None, "google_login": False, "accounts_enabled": False}


def test_other_account_endpoints_stay_503_when_disabled(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ACCOUNT_AUTH_ENABLED", False)

    assert client.get("/api/account/me").status_code == 503
    assert client.get("/api/account/state").status_code == 503
    login = client.post("/api/account/login", json={"email": "a@example.com", "password": "x" * 12})
    assert login.status_code == 503


def test_session_without_cookie_is_anonymous_when_enabled(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ACCOUNT_AUTH_ENABLED", True)

    response = client.get("/api/account/session")

    assert response.status_code == 200
    body = response.json()
    assert body["account"] is None
    assert body["accounts_enabled"] is True
    assert isinstance(body["google_login"], bool)
