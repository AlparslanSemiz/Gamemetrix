"""
Centralized settings loaded from environment / .env file.
Keys are never exposed outside this module — callers get bool/status, not raw values.
"""

import os
import re
from math import isfinite
from urllib.parse import urlparse


# Single source of truth for the outbound User-Agent. Providers block anonymous
# clients, so every integration identifies itself with this string.
USER_AGENT = "GameMetrix/0.1"

# Budget bucket for OpenCritic's search endpoint, which the provider limits far
# more tightly than its other routes.
OPENCRITIC_SEARCH_SOURCE = "OpenCritic:search"

# Providers that bill for overage. They get METERED_BUDGET_RESERVE_PERCENT
# instead of the ordinary reserve, because exceeding them costs money.
METERED_SOURCES: frozenset[str] = frozenset({"OpenCritic", OPENCRITIC_SEARCH_SOURCE})


def _csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        # ── Runtime / security ───────────────────────────────────────────────
        self.ENV: str = os.getenv("ENV", "development").strip().lower()
        self.JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ISSUER: str = os.getenv("JWT_ISSUER", "gamemetrix-api")
        self.JWT_AUDIENCE: str = os.getenv("JWT_AUDIENCE", "")
        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        )
        # Pseudonymisation salt for visitor/session hashes. Kept separate from
        # JWT_SECRET_KEY so rotating the signing key does not silently reset every
        # visitor identity (and so a signing key is not reused as a data-at-rest salt).
        # Falls back to the JWT secret to preserve existing hashes until set.
        self.ANALYTICS_SALT: str = os.getenv("ANALYTICS_SALT", "")
        self.ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "")
        self.ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "")
        self.PUBLIC_READ_RATE_LIMIT: str = os.getenv("PUBLIC_READ_RATE_LIMIT", "300/minute")
        self.AUTH_RATE_LIMIT: str = os.getenv("AUTH_RATE_LIMIT", "5/minute")
        self.RATE_LIMIT_STORAGE_URI: str = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
        self.ANALYTICS_STORE_RAW_IP: bool = os.getenv(
            "ANALYTICS_STORE_RAW_IP", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.ANALYTICS_TRUST_PROXY_HEADERS: bool = os.getenv(
            "ANALYTICS_TRUST_PROXY_HEADERS", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.ANALYTICS_RAW_IP_RETENTION_DAYS: int = max(
            1, int(os.getenv("ANALYTICS_RAW_IP_RETENTION_DAYS", "30"))
        )
        self.ACCOUNT_AUTH_ENABLED: bool = os.getenv(
            "ACCOUNT_AUTH_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.ACCOUNT_SESSION_DAYS: int = max(
            1, min(90, int(os.getenv("ACCOUNT_SESSION_DAYS", "30")))
        )
        self.ACCOUNT_BASE_URL: str = os.getenv(
            "ACCOUNT_BASE_URL", "http://localhost:5173"
        ).strip().rstrip("/")
        self.GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
        self.GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.GOOGLE_REDIRECT_URI: str = os.getenv(
            "GOOGLE_REDIRECT_URI",
            f"{self.ACCOUNT_BASE_URL}/api/account/oauth/google/callback",
        ).strip()
        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "").strip()
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
        self.SMTP_FROM_EMAIL: str = os.getenv(
            "SMTP_FROM_EMAIL", "accounts@gamemetrix.me"
        ).strip()
        self.SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "GameMetrix").strip()
        self.SMTP_START_TLS: bool = os.getenv(
            "SMTP_START_TLS", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.ACCOUNT_EMAIL_DELIVERY: str = os.getenv(
            "ACCOUNT_EMAIL_DELIVERY", "smtp" if self.is_production else "log"
        ).strip().lower()
        # ── API credentials ──────────────────────────────────────────────────
        self.IGDB_CLIENT_ID: str = os.getenv("IGDB_CLIENT_ID", "")
        self.IGDB_CLIENT_SECRET: str = os.getenv("IGDB_CLIENT_SECRET", "")
        self.RAWG_API_KEY: str = os.getenv("RAWG_API_KEY", "")
        self.OPENCRITIC_API_BASE: str = os.getenv(
            "OPENCRITIC_API_BASE", "https://opencritic-api.p.rapidapi.com"
        )
        self.OPENCRITIC_API_KEY: str = os.getenv("OPENCRITIC_API_KEY", "")
        self.RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
        self.RAPIDAPI_HOST: str = os.getenv(
            "RAPIDAPI_HOST", "opencritic-api.p.rapidapi.com"
        )
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.ITAD_API_KEY: str = os.getenv("ITAD_API_KEY", "")
        self.STEAM_WEB_API_KEY: str = os.getenv("STEAM_WEB_API_KEY", "")
        self.CHEAPSHARK_USER_AGENT: str = os.getenv("CHEAPSHARK_USER_AGENT", USER_AGENT)
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
        default_origins = (
            "https://gamemetrix.me,https://www.gamemetrix.me"
            if self.is_production
            else "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://gamemetrix.me"
        )
        self.CORS_ALLOW_ORIGINS: list[str] = _csv(os.getenv("CORS_ALLOW_ORIGINS", default_origins))
        # ── Background refresh tuning ─────────────────────────────────────────
        self.DAILY_RATING_REFRESH_LIMIT: int = int(
            os.getenv("DAILY_RATING_REFRESH_LIMIT", "250")
        )
        self.STARTUP_RATING_REFRESH_LIMIT: int = int(
            os.getenv("STARTUP_RATING_REFRESH_LIMIT", "0")
        )
        self.DAILY_METADATA_FIX_LIMIT: int = int(
            os.getenv("DAILY_METADATA_FIX_LIMIT", "500")
        )
        self.STARTUP_METADATA_FIX_LIMIT: int = int(
            os.getenv("STARTUP_METADATA_FIX_LIMIT", "0")
        )
        self.RATING_REFRESH_INTERVAL_SECONDS: int = int(
            os.getenv("RATING_REFRESH_INTERVAL_SECONDS", str(24 * 60 * 60))
        )
        self.RAWG_GAMES_URL: str = os.getenv(
            "RAWG_GAMES_URL", "https://api.rawg.io/api/games"
        )
        # ── Per-source daily request budgets ─────────────────────────────────
        # Override these when on a paid API plan.
        # OpenCritic (RapidAPI) is a METERED plan — exceeding it is billed, so its
        # ceilings mirror the provider's real limits and the search endpoint gets
        # its own, much tighter bucket. See PROVIDER_BUDGET_RESERVE_PERCENT below.
        self.OPENCRITIC_DAILY_LIMIT: int = int(os.getenv("OPENCRITIC_DAILY_LIMIT", "200"))
        self.OPENCRITIC_SEARCH_DAILY_LIMIT: int = int(
            os.getenv("OPENCRITIC_SEARCH_DAILY_LIMIT", "25")
        )
        self.IGDB_DAILY_LIMIT: int = int(os.getenv("IGDB_DAILY_LIMIT", "400"))
        self.RAWG_DAILY_LIMIT: int = int(os.getenv("RAWG_DAILY_LIMIT", "600"))
        self.STEAM_DAILY_LIMIT: int = int(os.getenv("STEAM_DAILY_LIMIT", "300"))
        self.STEAMSPY_DAILY_LIMIT: int = int(os.getenv("STEAMSPY_DAILY_LIMIT", "300"))
        self.CHEAPSHARK_DAILY_LIMIT: int = int(os.getenv("CHEAPSHARK_DAILY_LIMIT", "200"))
        self.FREETOGAME_DAILY_LIMIT: int = int(os.getenv("FREETOGAME_DAILY_LIMIT", "200"))
        self.ITAD_DAILY_LIMIT: int = int(os.getenv("ITAD_DAILY_LIMIT", "200"))
        self.HLTB_DAILY_LIMIT: int = int(os.getenv("HLTB_DAILY_LIMIT", "250"))
        self.HLTB_REQUEST_DELAY_SECONDS: float = max(
            0.5, float(os.getenv("HLTB_REQUEST_DELAY_SECONDS", "1.5"))
        )
        self.RAWG_MONTHLY_LIMIT: int = int(os.getenv("RAWG_MONTHLY_LIMIT", "20000"))
        self.ITAD_FIVE_MINUTE_LIMIT: int = int(os.getenv("ITAD_FIVE_MINUTE_LIMIT", "1000"))
        # Headroom kept below every provider ceiling so a miscount, a retry, or a
        # clock-skewed billing window cannot push actual usage past 100%.
        self.PROVIDER_BUDGET_RESERVE_PERCENT: int = max(
            0, min(50, int(os.getenv("PROVIDER_BUDGET_RESERVE_PERCENT", "15")))
        )
        # Metered providers reserve more: going over costs money, not just data.
        self.METERED_BUDGET_RESERVE_PERCENT: int = max(
            0, min(50, int(os.getenv("METERED_BUDGET_RESERVE_PERCENT", "30")))
        )
        # ── Per-source score weights (relative; default 1.0 = equal) ─────────
        # Higher values increase that source's share of the GameMetrix score.
        # Example: SCORE_WEIGHT_METACRITIC=2 gives Metacritic double influence.
        self.SCORE_WEIGHT_METACRITIC: float = float(os.getenv("SCORE_WEIGHT_METACRITIC", "1.0"))
        self.SCORE_WEIGHT_OPENCRITIC: float = float(os.getenv("SCORE_WEIGHT_OPENCRITIC", "1.0"))
        self.SCORE_WEIGHT_STEAM: float = float(os.getenv("SCORE_WEIGHT_STEAM", "1.0"))
        self.SCORE_WEIGHT_IGDB: float = float(os.getenv("SCORE_WEIGHT_IGDB", "1.0"))
        # ── Refresh-all scheduling ────────────────────────────────────────────
        self.REFRESH_ALL_INTERVAL_HOURS: float = float(
            os.getenv("REFRESH_ALL_INTERVAL_HOURS", "6")
        )
        self.REFRESH_ALL_CONCURRENCY: int = int(os.getenv("REFRESH_ALL_CONCURRENCY", "3"))
        self.REFRESH_ALL_INTER_GAME_DELAY: float = float(
            os.getenv("REFRESH_ALL_INTER_GAME_DELAY", "0.3")
        )
        # ── Metadata backfill scheduling ─────────────────────────────────────
        # Small source-aware batches fill missing covers, summaries, media,
        # external IDs, and store/detail metadata without exhausting API quotas.
        self.METADATA_BACKFILL_INTERVAL_MINUTES: float = float(
            os.getenv("METADATA_BACKFILL_INTERVAL_MINUTES", "30")
        )
        self.METADATA_BACKFILL_BATCH_SIZE: int = int(
            os.getenv("METADATA_BACKFILL_BATCH_SIZE", "24")
        )
        self.METADATA_BACKFILL_INTER_GAME_DELAY: float = float(
            os.getenv("METADATA_BACKFILL_INTER_GAME_DELAY", "0.5")
        )
        self.STARTUP_METADATA_BACKFILL_LIMIT: int = int(
            os.getenv("STARTUP_METADATA_BACKFILL_LIMIT", "12")
        )
        # ── HowLongToBeat playtime backfill ──────────────────────────────────
        # HLTB is scraped, not an official API — keep the cadence gentle.
        self.HLTB_BACKFILL_INTERVAL_MINUTES: float = float(
            os.getenv("HLTB_BACKFILL_INTERVAL_MINUTES", "60")
        )
        self.HLTB_BACKFILL_BATCH_SIZE: int = int(os.getenv("HLTB_BACKFILL_BATCH_SIZE", "50"))
        self.HLTB_BACKFILL_INTER_GAME_DELAY: float = float(
            os.getenv("HLTB_BACKFILL_INTER_GAME_DELAY", "1.0")
        )
        # ── Description shortening (summary_short) backfill ──────────────────
        self.SUMMARY_SHORTEN_INTERVAL_MINUTES: float = float(
            os.getenv("SUMMARY_SHORTEN_INTERVAL_MINUTES", "30")
        )
        self.SUMMARY_SHORTEN_BATCH_SIZE: int = int(os.getenv("SUMMARY_SHORTEN_BATCH_SIZE", "40"))
        self.SUMMARY_SHORTEN_STARTUP_LIMIT: int = int(
            os.getenv("SUMMARY_SHORTEN_STARTUP_LIMIT", "60")
        )
        # ── Endless (∞) playtime classification ──────────────────────────────
        # Roguelikes/MMOs/sandbox etc. have no completion time; flag them so they
        # stop reading as "missing HLTB". Heuristic first, Groq for the unclear ones.
        self.ENDLESS_BACKFILL_INTERVAL_MINUTES: float = float(
            os.getenv("ENDLESS_BACKFILL_INTERVAL_MINUTES", "120")
        )
        self.ENDLESS_BACKFILL_BATCH_SIZE: int = int(os.getenv("ENDLESS_BACKFILL_BATCH_SIZE", "60"))
        self.ENDLESS_USE_AI: bool = os.getenv("ENDLESS_USE_AI", "true").strip().lower() in {"1", "true", "yes", "on"}
        # ── Non-game cleanup ─────────────────────────────────────────────────
        # Detect asset packs / tools / demos that slipped through bulk imports.
        # Deletion only happens when algorithm AND AI agree and this flag is on;
        # otherwise candidates are quarantined by content_type, never removed.
        self.NONGAME_AUTODELETE_ENABLED: bool = os.getenv("NONGAME_AUTODELETE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.NONGAME_CLEANUP_BATCH_SIZE: int = int(os.getenv("NONGAME_CLEANUP_BATCH_SIZE", "40"))
        # ── Data fill orchestration ─────────────────────────────────────────
        self.DATA_FILL_ENABLED: bool = os.getenv("DATA_FILL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        self.DATA_FILL_TARGET_TOTAL: int = int(os.getenv("DATA_FILL_TARGET_TOTAL", "10000"))
        self.DATA_FILL_INTERVAL_HOURS: float = float(os.getenv("DATA_FILL_INTERVAL_HOURS", "24"))
        self.DATA_FILL_STARTUP_DELAY_SECONDS: int = int(os.getenv("DATA_FILL_STARTUP_DELAY_SECONDS", "120"))
        self.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE: int = int(os.getenv("DATA_FILL_PRIMARY_SCORE_BATCH_SIZE", "10000"))
        self.DATA_FILL_METADATA_BATCH_SIZE: int = int(os.getenv("DATA_FILL_METADATA_BATCH_SIZE", "48"))
        self.DATA_FILL_RATING_BATCH_SIZE: int = int(os.getenv("DATA_FILL_RATING_BATCH_SIZE", "48"))
        self.DATA_FILL_PRICE_BATCH_SIZE: int = int(os.getenv("DATA_FILL_PRICE_BATCH_SIZE", "48"))
        self.DATA_FILL_HLTB_TARGET: int = int(os.getenv("DATA_FILL_HLTB_TARGET", "5000"))
        self.DATA_FILL_INTER_GAME_DELAY: float = float(os.getenv("DATA_FILL_INTER_GAME_DELAY", "0.35"))
        # Ceiling on indexable game pages. This is a safety valve, not the quality
        # gate — services/seo.py already excludes thin, unrated, or image-less
        # entries. It defaulted to 100, which noindex'd all but the first hundred
        # games in a ~10k catalogue and capped organic traffic by construction.
        self.SEO_INDEX_LIMIT: int = max(1, min(50_000, int(os.getenv("SEO_INDEX_LIMIT", "50000"))))
        # ── Heavy admin jobs (imports, refresh-all) — peak-hour block ────────
        # Both 0 (default) disables the block entirely. To pause heavy jobs
        # 18:00-23:00 local time, set HEAVY_JOB_BLOCK_START_HOUR=18 and
        # HEAVY_JOB_BLOCK_END_HOUR=23.
        self.HEAVY_JOB_BLOCK_START_HOUR: int = int(os.getenv("HEAVY_JOB_BLOCK_START_HOUR", "0"))
        self.HEAVY_JOB_BLOCK_END_HOUR: int = int(os.getenv("HEAVY_JOB_BLOCK_END_HOUR", "0"))

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    def validate(self) -> None:
        errors: list[str] = []
        if self.ENV not in {"development", "test", "production"}:
            errors.append("ENV must be development, test, or production")
        if not self.DATABASE_URL.startswith("postgresql+psycopg://"):
            errors.append("DATABASE_URL must use postgresql+psycopg://")
        if self.JWT_ALGORITHM != "HS256":
            errors.append("JWT_ALGORITHM must be HS256")
        if not 1 <= self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 1440:
            errors.append("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440")
        rate_pattern = re.compile(r"^[1-9][0-9]*/(?:second|minute|hour|day)$")
        if not rate_pattern.fullmatch(self.PUBLIC_READ_RATE_LIMIT):
            errors.append("PUBLIC_READ_RATE_LIMIT must look like 300/minute")
        if not rate_pattern.fullmatch(self.AUTH_RATE_LIMIT):
            errors.append("AUTH_RATE_LIMIT must look like 5/minute")
        if self.ACCOUNT_EMAIL_DELIVERY not in {"log", "smtp"}:
            errors.append("ACCOUNT_EMAIL_DELIVERY must be log or smtp")
        if not 1 <= self.SMTP_PORT <= 65535:
            errors.append("SMTP_PORT must be between 1 and 65535")
        if bool(self.GOOGLE_CLIENT_ID) != bool(self.GOOGLE_CLIENT_SECRET):
            errors.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together")
        nonnegative_values = {
            "DAILY_RATING_REFRESH_LIMIT": self.DAILY_RATING_REFRESH_LIMIT,
            "STARTUP_RATING_REFRESH_LIMIT": self.STARTUP_RATING_REFRESH_LIMIT,
            "DAILY_METADATA_FIX_LIMIT": self.DAILY_METADATA_FIX_LIMIT,
            "STARTUP_METADATA_FIX_LIMIT": self.STARTUP_METADATA_FIX_LIMIT,
            "OPENCRITIC_DAILY_LIMIT": self.OPENCRITIC_DAILY_LIMIT,
            "IGDB_DAILY_LIMIT": self.IGDB_DAILY_LIMIT,
            "RAWG_DAILY_LIMIT": self.RAWG_DAILY_LIMIT,
            "STEAM_DAILY_LIMIT": self.STEAM_DAILY_LIMIT,
            "STEAMSPY_DAILY_LIMIT": self.STEAMSPY_DAILY_LIMIT,
            "CHEAPSHARK_DAILY_LIMIT": self.CHEAPSHARK_DAILY_LIMIT,
            "FREETOGAME_DAILY_LIMIT": self.FREETOGAME_DAILY_LIMIT,
            "ITAD_DAILY_LIMIT": self.ITAD_DAILY_LIMIT,
            "HLTB_DAILY_LIMIT": self.HLTB_DAILY_LIMIT,
            "RAWG_MONTHLY_LIMIT": self.RAWG_MONTHLY_LIMIT,
            "ITAD_FIVE_MINUTE_LIMIT": self.ITAD_FIVE_MINUTE_LIMIT,
            "STARTUP_METADATA_BACKFILL_LIMIT": self.STARTUP_METADATA_BACKFILL_LIMIT,
            "DATA_FILL_STARTUP_DELAY_SECONDS": self.DATA_FILL_STARTUP_DELAY_SECONDS,
        }
        invalid_nonnegative = sorted(name for name, value in nonnegative_values.items() if value < 0)
        if invalid_nonnegative:
            errors.append(f"These settings must be nonnegative: {', '.join(invalid_nonnegative)}")
        positive_values = {
            "RATING_REFRESH_INTERVAL_SECONDS": self.RATING_REFRESH_INTERVAL_SECONDS,
            "REFRESH_ALL_INTERVAL_HOURS": self.REFRESH_ALL_INTERVAL_HOURS,
            "REFRESH_ALL_CONCURRENCY": self.REFRESH_ALL_CONCURRENCY,
            "METADATA_BACKFILL_INTERVAL_MINUTES": self.METADATA_BACKFILL_INTERVAL_MINUTES,
            "METADATA_BACKFILL_BATCH_SIZE": self.METADATA_BACKFILL_BATCH_SIZE,
            "DATA_FILL_TARGET_TOTAL": self.DATA_FILL_TARGET_TOTAL,
            "DATA_FILL_INTERVAL_HOURS": self.DATA_FILL_INTERVAL_HOURS,
            "DATA_FILL_PRIMARY_SCORE_BATCH_SIZE": self.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE,
            "DATA_FILL_METADATA_BATCH_SIZE": self.DATA_FILL_METADATA_BATCH_SIZE,
            "DATA_FILL_RATING_BATCH_SIZE": self.DATA_FILL_RATING_BATCH_SIZE,
            "DATA_FILL_PRICE_BATCH_SIZE": self.DATA_FILL_PRICE_BATCH_SIZE,
            "DATA_FILL_HLTB_TARGET": self.DATA_FILL_HLTB_TARGET,
        }
        invalid_positive = sorted(
            name for name, value in positive_values.items() if not isfinite(float(value)) or value <= 0
        )
        if invalid_positive:
            errors.append(f"These settings must be positive and finite: {', '.join(invalid_positive)}")
        delay_values = {
            "REFRESH_ALL_INTER_GAME_DELAY": self.REFRESH_ALL_INTER_GAME_DELAY,
            "METADATA_BACKFILL_INTER_GAME_DELAY": self.METADATA_BACKFILL_INTER_GAME_DELAY,
            "DATA_FILL_INTER_GAME_DELAY": self.DATA_FILL_INTER_GAME_DELAY,
        }
        invalid_delays = sorted(
            name for name, value in delay_values.items() if not isfinite(value) or value < 0
        )
        if invalid_delays:
            errors.append(f"These delays must be nonnegative and finite: {', '.join(invalid_delays)}")
        score_modifiers = {
            "SCORE_WEIGHT_METACRITIC": self.SCORE_WEIGHT_METACRITIC,
            "SCORE_WEIGHT_OPENCRITIC": self.SCORE_WEIGHT_OPENCRITIC,
            "SCORE_WEIGHT_STEAM": self.SCORE_WEIGHT_STEAM,
            "SCORE_WEIGHT_IGDB": self.SCORE_WEIGHT_IGDB,
        }
        invalid_modifiers = sorted(
            name for name, value in score_modifiers.items() if not isfinite(value) or not 0 <= value <= 100
        )
        if invalid_modifiers:
            errors.append(f"These score modifiers must be finite and between 0 and 100: {', '.join(invalid_modifiers)}")
        if not 1 <= self.REFRESH_ALL_CONCURRENCY <= 32:
            errors.append("REFRESH_ALL_CONCURRENCY must be between 1 and 32")
        if not 0 <= self.HEAVY_JOB_BLOCK_START_HOUR <= 23 or not 0 <= self.HEAVY_JOB_BLOCK_END_HOUR <= 23:
            errors.append("HEAVY_JOB_BLOCK hours must be between 0 and 23")
        if self.is_production:
            if len(self.JWT_SECRET_KEY) < 32:
                errors.append("JWT_SECRET_KEY must contain at least 32 characters")
            if not self.ADMIN_USERNAME or not self.ADMIN_PASSWORD_HASH:
                errors.append("ADMIN_USERNAME and ADMIN_PASSWORD_HASH are required")
            elif not self.ADMIN_PASSWORD_HASH.startswith(("$2a$", "$2b$", "$2y$")):
                errors.append("ADMIN_PASSWORD_HASH must be a bcrypt hash")
            if not self.JWT_ISSUER or not self.JWT_AUDIENCE:
                errors.append("JWT_ISSUER and JWT_AUDIENCE are required")
            parsed = urlparse(self.ACCOUNT_BASE_URL)
            if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
                errors.append("ACCOUNT_BASE_URL must be an absolute HTTPS URL")
            if self.ACCOUNT_AUTH_ENABLED and self.ACCOUNT_EMAIL_DELIVERY != "smtp":
                errors.append("ACCOUNT_EMAIL_DELIVERY must be smtp when accounts are enabled")
            if self.ACCOUNT_AUTH_ENABLED and not self.SMTP_HOST:
                errors.append("SMTP_HOST is required when accounts are enabled")
            if not self.CORS_ALLOW_ORIGINS or any(
                urlparse(origin).scheme != "https"
                or not urlparse(origin).netloc
                or urlparse(origin).path not in {"", "/"}
                for origin in self.CORS_ALLOW_ORIGINS
            ):
                errors.append("CORS_ALLOW_ORIGINS must contain HTTPS origins only")
            if self.GOOGLE_CLIENT_ID:
                redirect = urlparse(self.GOOGLE_REDIRECT_URI)
                if redirect.scheme != "https" or redirect.netloc != parsed.netloc:
                    errors.append("GOOGLE_REDIRECT_URI must use the account HTTPS origin")
        if errors:
            raise RuntimeError("Invalid GameMetrix configuration: " + "; ".join(errors))

    def analytics_salt(self) -> str:
        """Salt for visitor/session pseudonyms; falls back to the JWT secret."""
        return self.ANALYTICS_SALT or self.JWT_SECRET_KEY or "gamemetrix-development-analytics-salt"

    # ── Provider request budgets ────────────────────────────────────────────
    # These live here rather than in the app lifespan so that every process —
    # scripts, tests, a REPL — gets the same ceilings, aliases, and windows.
    # A process without them would run with no monthly cap and an unaliased
    # Metacritic budget, i.e. double the intended provider traffic.

    def provider_daily_limits(self) -> dict[str, int]:
        return {
            "Metacritic": self.RAWG_DAILY_LIMIT,
            "OpenCritic": self.OPENCRITIC_DAILY_LIMIT,
            OPENCRITIC_SEARCH_SOURCE: self.OPENCRITIC_SEARCH_DAILY_LIMIT,
            "IGDB": self.IGDB_DAILY_LIMIT,
            "RAWG": self.RAWG_DAILY_LIMIT,
            "Steam": self.STEAM_DAILY_LIMIT,
            "SteamSpy": self.STEAMSPY_DAILY_LIMIT,
            "CheapShark": self.CHEAPSHARK_DAILY_LIMIT,
            "FreeToGame": self.FREETOGAME_DAILY_LIMIT,
            "ITAD": self.ITAD_DAILY_LIMIT,
            "HLTB": self.HLTB_DAILY_LIMIT,
        }

    def provider_budget_aliases(self) -> dict[str, str]:
        # Metacritic scores are fetched through the RAWG API with the same key,
        # so they must draw from one budget — separate budgets would let combined
        # traffic reach 2x the daily limit.
        return {"Metacritic": "RAWG"}

    def provider_window_limits(self) -> dict[str, list[tuple[str, int, int]]]:
        """source -> [(kind, request_limit, seconds)]"""
        return {
            "RAWG": [("monthly", self.RAWG_MONTHLY_LIMIT, 31 * 24 * 60 * 60)],
            "ITAD": [("rolling", self.ITAD_FIVE_MINUTE_LIMIT, 5 * 60)],
        }

    def budget_reserve_percent(self, source: str) -> int:
        if source in METERED_SOURCES:
            return max(self.PROVIDER_BUDGET_RESERVE_PERCENT, self.METERED_BUDGET_RESERVE_PERCENT)
        return self.PROVIDER_BUDGET_RESERVE_PERCENT

    # ── Configured checks — never return raw key values ─────────────────────

    def igdb_configured(self) -> bool:
        return bool(self.IGDB_CLIENT_ID and self.IGDB_CLIENT_SECRET)

    def rawg_configured(self) -> bool:
        return bool(self.RAWG_API_KEY)

    def opencritic_configured(self) -> bool:
        if "rapidapi" in self.OPENCRITIC_API_BASE.lower():
            return bool(self.RAPIDAPI_KEY)
        return bool(self.OPENCRITIC_API_KEY or self.RAPIDAPI_KEY)

    def groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY)

    def itad_configured(self) -> bool:
        return bool(self.ITAD_API_KEY)

    def steam_configured(self) -> bool:
        return bool(self.STEAM_WEB_API_KEY)

    def cheapshark_configured(self) -> bool:
        return True  # No key required


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
