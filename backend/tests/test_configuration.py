import pytest

from app.config import Settings


def test_production_rejects_weak_security_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    monkeypatch.setenv("ACCOUNT_AUTH_ENABLED", "true")
    monkeypatch.setenv("ACCOUNT_BASE_URL", "http://gamemetrix.me")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        Settings().validate()


def test_development_allows_log_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("ACCOUNT_EMAIL_DELIVERY", "log")
    Settings().validate()


def test_configuration_rejects_non_postgres_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///legacy.db")
    with pytest.raises(RuntimeError, match=r"postgresql\+psycopg"):
        Settings().validate()


def test_configuration_rejects_unsafe_numeric_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_FILL_PRICE_BATCH_SIZE", "0")
    monkeypatch.setenv("SCORE_WEIGHT_STEAM", "nan")
    with pytest.raises(RuntimeError, match="DATA_FILL_PRICE_BATCH_SIZE"):
        Settings().validate()


def test_opencritic_direct_and_rapidapi_credentials_stay_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCRITIC_API_BASE", "https://licensed.opencritic.example/api")
    monkeypatch.setenv("OPENCRITIC_API_KEY", "direct-license-key")
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    assert Settings().opencritic_configured() is True

    monkeypatch.setenv("OPENCRITIC_API_BASE", "https://opencritic-api.p.rapidapi.com")
    assert Settings().opencritic_configured() is False
    monkeypatch.setenv("RAPIDAPI_KEY", "rapidapi-subscription-key")
    assert Settings().opencritic_configured() is True
