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


def test_production_accepts_disabled_accounts_without_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("JWT_ISSUER", "gamemetrix-api")
    monkeypatch.setenv("JWT_AUDIENCE", "gamemetrix-admin")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        "$2b$12$123456789012345678901u12345678901234567890123456789012",
    )
    monkeypatch.setenv("ACCOUNT_AUTH_ENABLED", "false")
    monkeypatch.setenv("ACCOUNT_BASE_URL", "https://gamemetrix.me")
    monkeypatch.setenv("ACCOUNT_EMAIL_DELIVERY", "log")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "https://gamemetrix.me,https://www.gamemetrix.me",
    )

    Settings().validate()


def test_production_rejects_any_insecure_cors_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("JWT_ISSUER", "gamemetrix-api")
    monkeypatch.setenv("JWT_AUDIENCE", "gamemetrix-admin")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        "$2b$12$123456789012345678901u12345678901234567890123456789012",
    )
    monkeypatch.setenv("ACCOUNT_AUTH_ENABLED", "false")
    monkeypatch.setenv("ACCOUNT_BASE_URL", "https://gamemetrix.me")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://gamemetrix.me,http://localhost:5173")

    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        Settings().validate()


def test_development_allows_log_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("ACCOUNT_EMAIL_DELIVERY", "log")
    Settings().validate()


def test_full_catalog_maintenance_does_not_run_on_every_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STARTUP_CATALOG_MAINTENANCE_ENABLED", raising=False)

    assert Settings().STARTUP_CATALOG_MAINTENANCE_ENABLED is False


def test_catalog_repairs_default_to_a_bounded_memory_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CATALOG_REPAIR_BATCH_SIZE", raising=False)

    assert Settings().CATALOG_REPAIR_BATCH_SIZE <= 10


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


def test_rapidapi_opencritic_cannot_exceed_the_confirmed_free_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCRITIC_API_BASE", "https://opencritic-api.p.rapidapi.com")
    monkeypatch.setenv("OPENCRITIC_DAILY_LIMIT", "201")
    monkeypatch.setenv("OPENCRITIC_SEARCH_DAILY_LIMIT", "26")

    with pytest.raises(RuntimeError, match="OPENCRITIC_DAILY_LIMIT"):
        Settings().validate()


def test_ai_provider_order_is_centralized_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AI_PROVIDER_ORDER",
        "groq,gemini,cloudflare,openrouter",
    )
    settings = Settings()

    assert settings.AI_PROVIDER_ORDER == [
        "groq",
        "gemini",
        "cloudflare",
        "openrouter",
    ]

    monkeypatch.setenv("AI_PROVIDER_ORDER", "groq,gemini,groq")
    with pytest.raises(RuntimeError, match="AI_PROVIDER_ORDER"):
        Settings().validate()


def test_cloudflare_credentials_must_be_configured_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-only")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        Settings().validate()
