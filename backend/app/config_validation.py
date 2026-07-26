"""Settings validation, split out of `config.py` so loading and checking are separate.

Pure predicate logic over a `Settings` instance — reads no environment itself.
"""

from __future__ import annotations

import re
from math import isfinite
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .config import Settings

_RATE_LIMIT_RE = re.compile(r"^[1-9][0-9]*/(?:second|minute|hour|day)$")
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_MIN_JWT_SECRET_LENGTH = 32
_MAX_JWT_EXPIRE_MINUTES = 1440
_MAX_REFRESH_CONCURRENCY = 32
_MAX_HOUR = 23
_AI_PROVIDERS = frozenset({"groq", "gemini", "cloudflare", "openrouter"})
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9@._:/-]+$")
_CLOUDFLARE_ACCOUNT_ID_RE = re.compile(r"^[A-Fa-f0-9]{32}$")


def validate_settings(settings: "Settings") -> None:
    errors: list[str] = []
    _validate_core(settings, errors)
    _validate_numeric(settings, errors)
    if settings.is_production:
        _validate_production(settings, errors)
    if errors:
        raise RuntimeError("Invalid GameMetrix configuration: " + "; ".join(errors))


def _is_https_origin(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.path in {"", "/"}


def _validate_core(settings: "Settings", errors: list[str]) -> None:
    if settings.ENV not in {"development", "test", "production"}:
        errors.append("ENV must be development, test, or production")
    if not settings.DATABASE_URL.startswith("postgresql+psycopg://"):
        errors.append("DATABASE_URL must use postgresql+psycopg://")
    if settings.JWT_ALGORITHM != "HS256":
        errors.append("JWT_ALGORITHM must be HS256")
    if not 1 <= settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= _MAX_JWT_EXPIRE_MINUTES:
        errors.append("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440")
    if not _RATE_LIMIT_RE.fullmatch(settings.PUBLIC_READ_RATE_LIMIT):
        errors.append("PUBLIC_READ_RATE_LIMIT must look like 300/minute")
    if not _RATE_LIMIT_RE.fullmatch(settings.AUTH_RATE_LIMIT):
        errors.append("AUTH_RATE_LIMIT must look like 5/minute")
    if settings.ACCOUNT_EMAIL_DELIVERY not in {"log", "smtp"}:
        errors.append("ACCOUNT_EMAIL_DELIVERY must be log or smtp")
    if not 1 <= settings.SMTP_PORT <= 65535:
        errors.append("SMTP_PORT must be between 1 and 65535")
    if bool(settings.GOOGLE_CLIENT_ID) != bool(settings.GOOGLE_CLIENT_SECRET):
        errors.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together")
    if bool(settings.CLOUDFLARE_API_TOKEN) != bool(settings.CLOUDFLARE_ACCOUNT_ID):
        errors.append(
            "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be configured together"
        )
    if (
        not settings.AI_PROVIDER_ORDER
        or len(settings.AI_PROVIDER_ORDER) != len(set(settings.AI_PROVIDER_ORDER))
        or any(name not in _AI_PROVIDERS for name in settings.AI_PROVIDER_ORDER)
    ):
        errors.append(
            "AI_PROVIDER_ORDER must contain unique names chosen from "
            "groq, gemini, cloudflare, openrouter"
        )
    for name, model in {
        "GROQ_MODEL": settings.GROQ_MODEL,
        "GEMINI_MODEL": settings.GEMINI_MODEL,
        "CLOUDFLARE_MODEL": settings.CLOUDFLARE_MODEL,
        "OPENROUTER_MODEL": settings.OPENROUTER_MODEL,
    }.items():
        if not model or not _MODEL_NAME_RE.fullmatch(model):
            errors.append(f"{name} contains unsupported characters")
    if settings.CLOUDFLARE_ACCOUNT_ID and not _CLOUDFLARE_ACCOUNT_ID_RE.fullmatch(
        settings.CLOUDFLARE_ACCOUNT_ID
    ):
        errors.append("CLOUDFLARE_ACCOUNT_ID must be a 32-character hexadecimal ID")


def _validate_numeric(settings: "Settings", errors: list[str]) -> None:
    _flag_out_of_range(
        errors,
        "These settings must be nonnegative",
        _nonnegative_settings(settings),
        lambda value: value < 0,
    )
    _flag_out_of_range(
        errors,
        "These settings must be positive and finite",
        _positive_settings(settings),
        lambda value: not isfinite(float(value)) or value <= 0,
    )
    _flag_out_of_range(
        errors,
        "These delays must be nonnegative and finite",
        _delay_settings(settings),
        lambda value: not isfinite(value) or value < 0,
    )
    _flag_out_of_range(
        errors,
        "These score modifiers must be finite and between 0 and 100",
        _score_modifier_settings(settings),
        lambda value: not isfinite(value) or not 0 <= value <= 100,
    )
    if not 1 <= settings.REFRESH_ALL_CONCURRENCY <= _MAX_REFRESH_CONCURRENCY:
        errors.append("REFRESH_ALL_CONCURRENCY must be between 1 and 32")
    if not 0 <= settings.HEAVY_JOB_BLOCK_START_HOUR <= _MAX_HOUR or not 0 <= settings.HEAVY_JOB_BLOCK_END_HOUR <= _MAX_HOUR:
        errors.append("HEAVY_JOB_BLOCK hours must be between 0 and 23")


def _flag_out_of_range(errors, message, values, is_invalid) -> None:
    offenders = sorted(name for name, value in values.items() if is_invalid(value))
    if offenders:
        errors.append(f"{message}: {', '.join(offenders)}")


def _nonnegative_settings(s: "Settings") -> dict[str, float]:
    return {
        "DAILY_RATING_REFRESH_LIMIT": s.DAILY_RATING_REFRESH_LIMIT,
        "STARTUP_RATING_REFRESH_LIMIT": s.STARTUP_RATING_REFRESH_LIMIT,
        "DAILY_METADATA_FIX_LIMIT": s.DAILY_METADATA_FIX_LIMIT,
        "STARTUP_METADATA_FIX_LIMIT": s.STARTUP_METADATA_FIX_LIMIT,
        "OPENCRITIC_DAILY_LIMIT": s.OPENCRITIC_DAILY_LIMIT,
        "IGDB_DAILY_LIMIT": s.IGDB_DAILY_LIMIT,
        "RAWG_DAILY_LIMIT": s.RAWG_DAILY_LIMIT,
        "STEAM_DAILY_LIMIT": s.STEAM_DAILY_LIMIT,
        "STEAMSPY_DAILY_LIMIT": s.STEAMSPY_DAILY_LIMIT,
        "CHEAPSHARK_DAILY_LIMIT": s.CHEAPSHARK_DAILY_LIMIT,
        "FREETOGAME_DAILY_LIMIT": s.FREETOGAME_DAILY_LIMIT,
        "ITAD_DAILY_LIMIT": s.ITAD_DAILY_LIMIT,
        "HLTB_DAILY_LIMIT": s.HLTB_DAILY_LIMIT,
        "WIKIDATA_DAILY_LIMIT": s.WIKIDATA_DAILY_LIMIT,
        "GAMEBRAIN_DAILY_LIMIT": s.GAMEBRAIN_DAILY_LIMIT,
        "GROQ_DAILY_LIMIT": s.GROQ_DAILY_LIMIT,
        "GROQ_DAILY_TOKEN_LIMIT": s.GROQ_DAILY_TOKEN_LIMIT,
        "RAWG_MONTHLY_LIMIT": s.RAWG_MONTHLY_LIMIT,
        "ITAD_FIVE_MINUTE_LIMIT": s.ITAD_FIVE_MINUTE_LIMIT,
        "STARTUP_METADATA_BACKFILL_LIMIT": s.STARTUP_METADATA_BACKFILL_LIMIT,
        "SUMMARY_SHORTEN_STARTUP_LIMIT": s.SUMMARY_SHORTEN_STARTUP_LIMIT,
        "SUMMARY_QUALITY_AI_LIMIT": s.SUMMARY_QUALITY_AI_LIMIT,
        "DATA_FILL_STARTUP_DELAY_SECONDS": s.DATA_FILL_STARTUP_DELAY_SECONDS,
    }


def _positive_settings(s: "Settings") -> dict[str, float]:
    return {
        "RATING_REFRESH_INTERVAL_SECONDS": s.RATING_REFRESH_INTERVAL_SECONDS,
        "REFRESH_ALL_INTERVAL_HOURS": s.REFRESH_ALL_INTERVAL_HOURS,
        "REFRESH_ALL_CONCURRENCY": s.REFRESH_ALL_CONCURRENCY,
        "METADATA_BACKFILL_INTERVAL_MINUTES": s.METADATA_BACKFILL_INTERVAL_MINUTES,
        "METADATA_BACKFILL_BATCH_SIZE": s.METADATA_BACKFILL_BATCH_SIZE,
        "DATA_FILL_TARGET_TOTAL": s.DATA_FILL_TARGET_TOTAL,
        "DATA_FILL_INTERVAL_HOURS": s.DATA_FILL_INTERVAL_HOURS,
        "DATA_FILL_PRIMARY_SCORE_BATCH_SIZE": s.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE,
        "DATA_FILL_METADATA_BATCH_SIZE": s.DATA_FILL_METADATA_BATCH_SIZE,
        "DATA_FILL_RATING_BATCH_SIZE": s.DATA_FILL_RATING_BATCH_SIZE,
        "DATA_FILL_PRICE_BATCH_SIZE": s.DATA_FILL_PRICE_BATCH_SIZE,
        "DATA_FILL_HLTB_TARGET": s.DATA_FILL_HLTB_TARGET,
        "AI_PROVIDER_TIMEOUT_SECONDS": s.AI_PROVIDER_TIMEOUT_SECONDS,
        "AI_BACKGROUND_DEADLINE_SECONDS": s.AI_BACKGROUND_DEADLINE_SECONDS,
        "AI_INTERACTIVE_DEADLINE_SECONDS": s.AI_INTERACTIVE_DEADLINE_SECONDS,
    }


def _delay_settings(s: "Settings") -> dict[str, float]:
    return {
        "REFRESH_ALL_INTER_GAME_DELAY": s.REFRESH_ALL_INTER_GAME_DELAY,
        "METADATA_BACKFILL_INTER_GAME_DELAY": s.METADATA_BACKFILL_INTER_GAME_DELAY,
        "DATA_FILL_INTER_GAME_DELAY": s.DATA_FILL_INTER_GAME_DELAY,
        "GEMINI_MIN_REQUEST_INTERVAL_SECONDS": s.GEMINI_MIN_REQUEST_INTERVAL_SECONDS,
    }


def _score_modifier_settings(s: "Settings") -> dict[str, float]:
    return {
        "SCORE_WEIGHT_METACRITIC": s.SCORE_WEIGHT_METACRITIC,
        "SCORE_WEIGHT_OPENCRITIC": s.SCORE_WEIGHT_OPENCRITIC,
        "SCORE_WEIGHT_STEAM": s.SCORE_WEIGHT_STEAM,
        "SCORE_WEIGHT_IGDB": s.SCORE_WEIGHT_IGDB,
    }


def _validate_production(settings: "Settings", errors: list[str]) -> None:
    if len(settings.JWT_SECRET_KEY) < _MIN_JWT_SECRET_LENGTH:
        errors.append("JWT_SECRET_KEY must contain at least 32 characters")
    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD_HASH:
        errors.append("ADMIN_USERNAME and ADMIN_PASSWORD_HASH are required")
    elif not settings.ADMIN_PASSWORD_HASH.startswith(_BCRYPT_PREFIXES):
        errors.append("ADMIN_PASSWORD_HASH must be a bcrypt hash")
    if not settings.JWT_ISSUER or not settings.JWT_AUDIENCE:
        errors.append("JWT_ISSUER and JWT_AUDIENCE are required")
    if not _is_https_origin(settings.ACCOUNT_BASE_URL):
        errors.append("ACCOUNT_BASE_URL must be an absolute HTTPS URL")
    if settings.ACCOUNT_AUTH_ENABLED and settings.ACCOUNT_EMAIL_DELIVERY != "smtp":
        errors.append("ACCOUNT_EMAIL_DELIVERY must be smtp when accounts are enabled")
    if settings.ACCOUNT_AUTH_ENABLED and not settings.SMTP_HOST:
        errors.append("SMTP_HOST is required when accounts are enabled")
    if not settings.CORS_ALLOW_ORIGINS or any(
        not _is_https_origin(origin) for origin in settings.CORS_ALLOW_ORIGINS
    ):
        errors.append("CORS_ALLOW_ORIGINS must contain HTTPS origins only")
    if settings.GOOGLE_CLIENT_ID:
        redirect = urlparse(settings.GOOGLE_REDIRECT_URI)
        if redirect.scheme != "https" or redirect.netloc != urlparse(settings.ACCOUNT_BASE_URL).netloc:
            errors.append("GOOGLE_REDIRECT_URI must use the account HTTPS origin")
