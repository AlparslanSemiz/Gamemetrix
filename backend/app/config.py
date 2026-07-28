"""
Centralized settings loaded from environment / .env file.
Keys are never exposed outside this module — callers get bool/status, not raw values.
"""

import os

from .config_validation import validate_settings

# Single source of truth for the outbound User-Agent. Providers block anonymous
# clients, so every integration identifies itself with this string.
USER_AGENT = "GameMetrix/0.1"

# Budget bucket for OpenCritic's search endpoint, which the provider limits far
# more tightly than its other routes.
OPENCRITIC_SEARCH_SOURCE = "OpenCritic:search"

# Providers with a possible monetary charge (for example bandwidth overage).
# OpenCritic's request/search objects are hard-limited; its configured local
# caps already include their own headroom below those provider ceilings.
METERED_SOURCES: frozenset[str] = frozenset({"OpenCritic", OPENCRITIC_SEARCH_SOURCE})

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_RESERVE_PERCENT = 50
_MAX_SESSION_DAYS = 90
_SECONDS_PER_DAY = 24 * 60 * 60


def _csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_stripped(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else float(default)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class Settings:
    def __init__(self) -> None:
        self._load_runtime_settings()
        self._load_provider_settings()
        self._load_refresh_settings()
        self._load_provider_budget_settings()
        self._load_scoring_and_refresh_all_settings()
        self._load_backfill_settings()
        self._load_data_fill_settings()

    def _load_runtime_settings(self) -> None:
        # ── Runtime / security ───────────────────────────────────────────────
        self.ENV: str = _env_stripped("ENV", "development").lower()
        self.JWT_SECRET_KEY: str = _env("JWT_SECRET_KEY")
        self.JWT_ALGORITHM: str = _env("JWT_ALGORITHM", "HS256")
        self.JWT_ISSUER: str = _env("JWT_ISSUER", "gamemetrix-api")
        self.JWT_AUDIENCE: str = _env("JWT_AUDIENCE")
        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = _env_int("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
        # Pseudonymisation salt for visitor/session hashes. Kept separate from
        # JWT_SECRET_KEY so rotating the signing key does not silently reset every
        # visitor identity (and so a signing key is not reused as a data-at-rest salt).
        # Falls back to the JWT secret to preserve existing hashes until set.
        self.ANALYTICS_SALT: str = _env("ANALYTICS_SALT")
        self.ADMIN_USERNAME: str = _env("ADMIN_USERNAME")
        self.ADMIN_PASSWORD_HASH: str = _env("ADMIN_PASSWORD_HASH")
        self.PUBLIC_READ_RATE_LIMIT: str = _env("PUBLIC_READ_RATE_LIMIT", "300/minute")
        self.AUTH_RATE_LIMIT: str = _env("AUTH_RATE_LIMIT", "5/minute")
        self.RATE_LIMIT_STORAGE_URI: str = _env("RATE_LIMIT_STORAGE_URI", "memory://")
        self.ANALYTICS_STORE_RAW_IP: bool = _env_bool("ANALYTICS_STORE_RAW_IP", False)
        self.ANALYTICS_TRUST_PROXY_HEADERS: bool = _env_bool("ANALYTICS_TRUST_PROXY_HEADERS", False)
        self.ANALYTICS_RAW_IP_RETENTION_DAYS: int = max(1, _env_int("ANALYTICS_RAW_IP_RETENTION_DAYS", 30))
        self.ACCOUNT_AUTH_ENABLED: bool = _env_bool("ACCOUNT_AUTH_ENABLED", True)
        self.ACCOUNT_SESSION_DAYS: int = _clamp(_env_int("ACCOUNT_SESSION_DAYS", 30), 1, _MAX_SESSION_DAYS)
        self.ACCOUNT_BASE_URL: str = _env_stripped("ACCOUNT_BASE_URL", "http://localhost:5173").rstrip("/")
        self.GOOGLE_CLIENT_ID: str = _env("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET: str = _env("GOOGLE_CLIENT_SECRET")
        self.GOOGLE_REDIRECT_URI: str = _env_stripped(
            "GOOGLE_REDIRECT_URI",
            f"{self.ACCOUNT_BASE_URL}/api/account/oauth/google/callback",
        )
        self.SMTP_HOST: str = _env_stripped("SMTP_HOST")
        self.SMTP_PORT: int = _env_int("SMTP_PORT", 587)
        self.SMTP_USERNAME: str = _env("SMTP_USERNAME")
        self.SMTP_PASSWORD: str = _env("SMTP_PASSWORD")
        self.SMTP_FROM_EMAIL: str = _env_stripped("SMTP_FROM_EMAIL", "accounts@gamemetrix.me")
        self.SMTP_FROM_NAME: str = _env_stripped("SMTP_FROM_NAME", "GameMetrix")
        self.SMTP_START_TLS: bool = _env_bool("SMTP_START_TLS", True)
        self.ACCOUNT_EMAIL_DELIVERY: str = _env_stripped(
            "ACCOUNT_EMAIL_DELIVERY", "smtp" if self.is_production else "log"
        ).lower()

    def _load_provider_settings(self) -> None:
        # ── API credentials ──────────────────────────────────────────────────
        self.IGDB_CLIENT_ID: str = _env("IGDB_CLIENT_ID")
        self.IGDB_CLIENT_SECRET: str = _env("IGDB_CLIENT_SECRET")
        self.RAWG_API_KEY: str = _env("RAWG_API_KEY")
        self.OPENCRITIC_API_BASE: str = _env(
            "OPENCRITIC_API_BASE", "https://opencritic-api.p.rapidapi.com"
        )
        self.OPENCRITIC_API_KEY: str = _env("OPENCRITIC_API_KEY")
        self.RAPIDAPI_KEY: str = _env("RAPIDAPI_KEY")
        self.RAPIDAPI_HOST: str = _env("RAPIDAPI_HOST", "opencritic-api.p.rapidapi.com")
        self.GROQ_API_KEY: str = _env("GROQ_API_KEY")
        self.GROQ_MODEL: str = _env("GROQ_MODEL", "openai/gpt-oss-20b")
        self.GROQ_MIN_REQUEST_INTERVAL_SECONDS: float = max(
            12.0, _env_float("GROQ_MIN_REQUEST_INTERVAL_SECONDS", 12.0)
        )
        self.GEMINI_API_KEY: str = _env("GEMINI_API_KEY")
        self.GEMINI_MODEL: str = _env("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.GEMINI_MIN_REQUEST_INTERVAL_SECONDS: float = _env_float(
            "GEMINI_MIN_REQUEST_INTERVAL_SECONDS", 6.0
        )
        self.CLOUDFLARE_API_TOKEN: str = _env("CLOUDFLARE_API_TOKEN")
        self.CLOUDFLARE_ACCOUNT_ID: str = _env_stripped("CLOUDFLARE_ACCOUNT_ID")
        self.CLOUDFLARE_MODEL: str = _env(
            "CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-20b"
        )
        self.OPENROUTER_API_KEY: str = _env("OPENROUTER_API_KEY")
        self.OPENROUTER_MODEL: str = _env("OPENROUTER_MODEL", "openrouter/free")
        self.AI_PROVIDER_ORDER: list[str] = [
            item.casefold()
            for item in _csv(
                _env(
                    "AI_PROVIDER_ORDER",
                    "groq,gemini,cloudflare,openrouter",
                )
            )
        ]
        self.AI_PROVIDER_TIMEOUT_SECONDS: float = _env_float(
            "AI_PROVIDER_TIMEOUT_SECONDS", 10.0
        )
        self.AI_BACKGROUND_DEADLINE_SECONDS: float = _env_float(
            "AI_BACKGROUND_DEADLINE_SECONDS", 60.0
        )
        self.AI_INTERACTIVE_DEADLINE_SECONDS: float = _env_float(
            "AI_INTERACTIVE_DEADLINE_SECONDS", 15.0
        )
        self.AI_MAX_CONCURRENCY: int = _clamp(_env_int("AI_MAX_CONCURRENCY", 2), 1, 2)
        self.AI_MAX_PROMPT_CHARS: int = _clamp(
            _env_int("AI_MAX_PROMPT_CHARS", 16_000),
            1_000,
            16_000,
        )
        self.AI_MAX_OUTPUT_TOKENS: int = _clamp(
            _env_int("AI_MAX_OUTPUT_TOKENS", 1_024),
            64,
            1_024,
        )
        self.ITAD_API_KEY: str = _env("ITAD_API_KEY")
        self.STEAM_WEB_API_KEY: str = _env("STEAM_WEB_API_KEY")
        self.GAMEBRAIN_API_KEY: str = _env("GAMEBRAIN_API_KEY")
        # GameBrain's free plan is non-commercial only. A key alone must never
        # silently enable it on a commercial deployment.
        self.GAMEBRAIN_NONCOMMERCIAL_ENABLED: bool = _env_bool(
            "GAMEBRAIN_NONCOMMERCIAL_ENABLED", False
        )
        self.GAMEBRAIN_CACHE_PERMISSION_GRANTED: bool = _env_bool(
            "GAMEBRAIN_CACHE_PERMISSION_GRANTED", False
        )
        self.CHEAPSHARK_USER_AGENT: str = _env("CHEAPSHARK_USER_AGENT", USER_AGENT)
        self.DATABASE_URL: str = _env_stripped("DATABASE_URL")
        default_origins = (
            "https://gamemetrix.me,https://www.gamemetrix.me"
            if self.is_production
            else "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://gamemetrix.me"
        )
        self.CORS_ALLOW_ORIGINS: list[str] = _csv(_env("CORS_ALLOW_ORIGINS", default_origins))

    def _load_refresh_settings(self) -> None:
        # ── Background refresh tuning ─────────────────────────────────────────
        self.DAILY_RATING_REFRESH_LIMIT: int = _env_int("DAILY_RATING_REFRESH_LIMIT", 250)
        self.STARTUP_RATING_REFRESH_LIMIT: int = _env_int("STARTUP_RATING_REFRESH_LIMIT", 0)
        self.DAILY_METADATA_FIX_LIMIT: int = _env_int("DAILY_METADATA_FIX_LIMIT", 500)
        self.STARTUP_METADATA_FIX_LIMIT: int = _env_int("STARTUP_METADATA_FIX_LIMIT", 0)
        self.RATING_REFRESH_INTERVAL_SECONDS: int = _env_int(
            "RATING_REFRESH_INTERVAL_SECONDS", _SECONDS_PER_DAY
        )
        self.RAWG_GAMES_URL: str = _env("RAWG_GAMES_URL", "https://api.rawg.io/api/games")

    def _load_provider_budget_settings(self) -> None:
        # ── Per-source daily request budgets ─────────────────────────────────
        # The confirmed RapidAPI Basic plan hard-limits 200 total requests/day,
        # 25 searches/day, and 4 requests/second. Local defaults retain one
        # search, ten requests, and one request/second of headroom.
        self.OPENCRITIC_DAILY_LIMIT: int = _env_int("OPENCRITIC_DAILY_LIMIT", 190)
        self.OPENCRITIC_SEARCH_DAILY_LIMIT: int = _env_int(
            "OPENCRITIC_SEARCH_DAILY_LIMIT", 24
        )
        self.OPENCRITIC_PER_SECOND_LIMIT: int = _env_int(
            "OPENCRITIC_PER_SECOND_LIMIT", 3
        )
        # IGDB (Twitch, ~4 req/s, no daily quota) and Steam (public endpoint, no
        # fixed daily cap) sit far below their real ceilings, so their budgets are
        # raised well above RAWG's to speed primary-score coverage at no cost.
        self.IGDB_DAILY_LIMIT: int = _env_int("IGDB_DAILY_LIMIT", 20_000)
        self.RAWG_DAILY_LIMIT: int = _env_int("RAWG_DAILY_LIMIT", 600)
        self.STEAM_DAILY_LIMIT: int = _env_int("STEAM_DAILY_LIMIT", 10_000)
        self.STEAMSPY_DAILY_LIMIT: int = _env_int("STEAMSPY_DAILY_LIMIT", 300)
        self.CHEAPSHARK_DAILY_LIMIT: int = _env_int("CHEAPSHARK_DAILY_LIMIT", 200)
        self.FREETOGAME_DAILY_LIMIT: int = _env_int("FREETOGAME_DAILY_LIMIT", 200)
        self.ITAD_DAILY_LIMIT: int = _env_int("ITAD_DAILY_LIMIT", 200)
        self.HLTB_DAILY_LIMIT: int = _env_int("HLTB_DAILY_LIMIT", 250)
        self.WIKIDATA_DAILY_LIMIT: int = _env_int("WIKIDATA_DAILY_LIMIT", 200)
        # Groq's free gpt-oss-20b tier allows 1,000 requests but only 200,000
        # tokens a day, and our catalog prompts exhaust the tokens first — so the
        # token ceiling is the real budget and the request count is a backstop.
        # Both are shared across summaries, quality review, endless detection and
        # reranking. Raise GROQ_DAILY_TOKEN_LIMIT to the tier's TPD when on a
        # paid plan; neither value is capped in code.
        self.GROQ_DAILY_LIMIT: int = _env_int("GROQ_DAILY_LIMIT", 1000)
        self.GROQ_DAILY_TOKEN_LIMIT: int = _env_int("GROQ_DAILY_TOKEN_LIMIT", 200_000)
        self.GEMINI_DAILY_LIMIT: int = _env_int("GEMINI_DAILY_LIMIT", 100)
        self.GEMINI_DAILY_TOKEN_LIMIT: int = _env_int("GEMINI_DAILY_TOKEN_LIMIT", 100_000)
        self.CLOUDFLARE_AI_DAILY_LIMIT: int = _env_int("CLOUDFLARE_AI_DAILY_LIMIT", 100)
        self.CLOUDFLARE_AI_DAILY_TOKEN_LIMIT: int = _env_int(
            "CLOUDFLARE_AI_DAILY_TOKEN_LIMIT",
            100_000,
        )
        self.OPENROUTER_DAILY_LIMIT: int = _env_int("OPENROUTER_DAILY_LIMIT", 50)
        self.OPENROUTER_DAILY_TOKEN_LIMIT: int = _env_int(
            "OPENROUTER_DAILY_TOKEN_LIMIT",
            100_000,
        )
        # Free GameBrain accounts get 50 tokens/day. Keep this hard default below
        # that ceiling even when the global reserve is explicitly set to zero.
        self.GAMEBRAIN_DAILY_LIMIT: int = _clamp(
            _env_int("GAMEBRAIN_DAILY_LIMIT", 40), 1, 50
        )
        self.HLTB_REQUEST_DELAY_SECONDS: float = max(0.5, _env_float("HLTB_REQUEST_DELAY_SECONDS", 1.5))
        self.RAWG_MONTHLY_LIMIT: int = _env_int("RAWG_MONTHLY_LIMIT", 20000)
        # RAWG accounts can renew on an account-specific day rather than the
        # first of the calendar month. GameMetrix's current key renews on day 25.
        self.RAWG_MONTHLY_RESET_DAY: int = _clamp(
            _env_int("RAWG_MONTHLY_RESET_DAY", 25), 1, 28
        )
        self.ITAD_FIVE_MINUTE_LIMIT: int = _env_int("ITAD_FIVE_MINUTE_LIMIT", 1000)
        # Headroom kept below every provider ceiling so a miscount, a retry, or a
        # clock-skewed billing window cannot push actual usage past 100%.
        self.PROVIDER_BUDGET_RESERVE_PERCENT: int = _clamp(
            _env_int("PROVIDER_BUDGET_RESERVE_PERCENT", 15), 0, _MAX_RESERVE_PERCENT
        )
        # Metered providers reserve more: going over costs money, not just data.
        self.METERED_BUDGET_RESERVE_PERCENT: int = _clamp(
            _env_int("METERED_BUDGET_RESERVE_PERCENT", 30), 0, _MAX_RESERVE_PERCENT
        )

    def _load_scoring_and_refresh_all_settings(self) -> None:
        # ── Per-source score weights (relative; default 1.0 = equal) ─────────
        # Higher values increase that source's share of the GameMetrix score.
        # Example: SCORE_WEIGHT_METACRITIC=2 gives Metacritic double influence.
        self.SCORE_WEIGHT_METACRITIC: float = _env_float("SCORE_WEIGHT_METACRITIC", 1.0)
        self.SCORE_WEIGHT_OPENCRITIC: float = _env_float("SCORE_WEIGHT_OPENCRITIC", 1.0)
        self.SCORE_WEIGHT_STEAM: float = _env_float("SCORE_WEIGHT_STEAM", 1.0)
        self.SCORE_WEIGHT_IGDB: float = _env_float("SCORE_WEIGHT_IGDB", 1.0)
        # ── Refresh-all scheduling ────────────────────────────────────────────
        self.REFRESH_ALL_INTERVAL_HOURS: float = _env_float("REFRESH_ALL_INTERVAL_HOURS", 6)
        self.REFRESH_ALL_CONCURRENCY: int = _env_int("REFRESH_ALL_CONCURRENCY", 3)
        self.REFRESH_ALL_INTER_GAME_DELAY: float = _env_float("REFRESH_ALL_INTER_GAME_DELAY", 0.3)

    def _load_backfill_settings(self) -> None:
        # ── Metadata backfill scheduling ─────────────────────────────────────
        # Small source-aware batches fill missing covers, summaries, media,
        # external IDs, and store/detail metadata without exhausting API quotas.
        self.METADATA_BACKFILL_INTERVAL_MINUTES: float = _env_float("METADATA_BACKFILL_INTERVAL_MINUTES", 30)
        self.METADATA_BACKFILL_BATCH_SIZE: int = _env_int("METADATA_BACKFILL_BATCH_SIZE", 24)
        self.METADATA_BACKFILL_INTER_GAME_DELAY: float = _env_float("METADATA_BACKFILL_INTER_GAME_DELAY", 0.5)
        # The ordered data-fill job owns the first provider budget after boot.
        # A separate startup metadata batch would race it and spend RAWG before
        # free CheapShark/IGDB/Wikidata passes have run.
        self.STARTUP_METADATA_BACKFILL_LIMIT: int = _env_int(
            "STARTUP_METADATA_BACKFILL_LIMIT", 0
        )
        # ── HowLongToBeat playtime backfill ──────────────────────────────────
        # HLTB is scraped, not an official API — keep the cadence gentle.
        self.HLTB_BACKFILL_INTERVAL_MINUTES: float = _env_float("HLTB_BACKFILL_INTERVAL_MINUTES", 60)
        self.HLTB_BACKFILL_BATCH_SIZE: int = _env_int("HLTB_BACKFILL_BATCH_SIZE", 50)
        self.HLTB_BACKFILL_INTER_GAME_DELAY: float = _env_float("HLTB_BACKFILL_INTER_GAME_DELAY", 1.0)
        # ── Description audit + shortening backfill ──────────────────────────
        # Each cycle re-checks a slice of the catalog: deterministic clean-up is
        # free, so the batch can be wide, while AI calls are capped per batch.
        # GROQ_DAILY_LIMIT is the real ceiling — it is shared with catalog
        # quality, endless detection and reranking.
        self.SUMMARY_SHORTEN_INTERVAL_MINUTES: float = _env_float("SUMMARY_SHORTEN_INTERVAL_MINUTES", 30)
        self.SUMMARY_SHORTEN_BATCH_SIZE: int = _env_int("SUMMARY_SHORTEN_BATCH_SIZE", 40)
        self.SUMMARY_SHORTEN_STARTUP_LIMIT: int = _env_int(
            "SUMMARY_SHORTEN_STARTUP_LIMIT", 0
        )
        self.SUMMARY_QUALITY_AI_LIMIT: int = _env_int("SUMMARY_QUALITY_AI_LIMIT", 4)
        # ── Endless (∞) playtime classification ──────────────────────────────
        # Roguelikes/MMOs/sandbox etc. have no completion time; flag them so they
        # stop reading as "missing HLTB". Heuristic first, Groq for the unclear ones.
        self.ENDLESS_BACKFILL_INTERVAL_MINUTES: float = _env_float("ENDLESS_BACKFILL_INTERVAL_MINUTES", 120)
        self.ENDLESS_BACKFILL_BATCH_SIZE: int = _env_int("ENDLESS_BACKFILL_BATCH_SIZE", 60)
        self.ENDLESS_USE_AI: bool = _env_bool("ENDLESS_USE_AI", True)
        # ── "Games like X" AI re-rank ────────────────────────────────────────
        # Off by default: the heuristic ranker stays authoritative. When on and
        # Groq is configured, Groq reorders the top heuristic candidates on the
        # game detail page. Never touches any score — display order only.
        self.SIMILARITY_USE_AI: bool = _env_bool("SIMILARITY_USE_AI", False)
        self.SIMILARITY_AI_POOL: int = _env_int("SIMILARITY_AI_POOL", 20)
        self.SIMILARITY_AI_DAILY_LIMIT: int = _env_int(
            "SIMILARITY_AI_DAILY_LIMIT",
            25,
        )
        self.SIMILARITY_AI_MIN_INTERVAL_SECONDS: float = max(
            1.0,
            _env_float("SIMILARITY_AI_MIN_INTERVAL_SECONDS", 2.0),
        )
        # ── Catalog quality review ───────────────────────────────────────────
        # Deterministic signals select suspicious titles, descriptions and core
        # metadata for advisory AI review. Only a separate authenticated admin
        # decision may approve, quarantine, or delete a catalog row.
        self.CATALOG_QUALITY_BATCH_SIZE: int = _env_int("CATALOG_QUALITY_BATCH_SIZE", 40)
        self.CATALOG_REPAIR_BATCH_SIZE: int = _env_int("CATALOG_REPAIR_BATCH_SIZE", 10)

    def _load_data_fill_settings(self) -> None:
        # ── Data fill orchestration ─────────────────────────────────────────
        self.STARTUP_CATALOG_MAINTENANCE_ENABLED: bool = _env_bool(
            "STARTUP_CATALOG_MAINTENANCE_ENABLED", False
        )
        self.DATA_FILL_ENABLED: bool = _env_bool("DATA_FILL_ENABLED", True)
        self.DATA_FILL_TARGET_TOTAL: int = _env_int("DATA_FILL_TARGET_TOTAL", 50000)
        self.DATA_FILL_INTERVAL_HOURS: float = _env_float("DATA_FILL_INTERVAL_HOURS", 24)
        self.DATA_FILL_STARTUP_DELAY_SECONDS: int = _env_int("DATA_FILL_STARTUP_DELAY_SECONDS", 120)
        self.DATA_FILL_PRIMARY_SCORE_BATCH_SIZE: int = _env_int("DATA_FILL_PRIMARY_SCORE_BATCH_SIZE", 10000)
        self.DATA_FILL_SYSTEM_REQUIREMENTS_BATCH_SIZE: int = _env_int(
            "DATA_FILL_SYSTEM_REQUIREMENTS_BATCH_SIZE", 3000
        )
        self.DATA_FILL_METADATA_BATCH_SIZE: int = _env_int("DATA_FILL_METADATA_BATCH_SIZE", 48)
        self.DATA_FILL_RATING_BATCH_SIZE: int = _env_int("DATA_FILL_RATING_BATCH_SIZE", 48)
        self.DATA_FILL_PRICE_BATCH_SIZE: int = _env_int("DATA_FILL_PRICE_BATCH_SIZE", 48)
        self.DATA_FILL_HLTB_TARGET: int = _env_int("DATA_FILL_HLTB_TARGET", 5000)
        self.DATA_FILL_INTER_GAME_DELAY: float = _env_float("DATA_FILL_INTER_GAME_DELAY", 0.35)
        # Publish search-facing game pages in reviewed cohorts. The quality gate
        # still excludes thin, unrated, or image-less entries; this ceiling avoids
        # presenting tens of thousands of API-generated pages to crawlers at once.
        self.SEO_INDEX_LIMIT: int = _clamp(_env_int("SEO_INDEX_LIMIT", 500), 1, 50_000)
        # ── Heavy admin jobs (imports, refresh-all) — peak-hour block ────────
        # Both 0 (default) disables the block entirely. To pause heavy jobs
        # 18:00-23:00 local time, set HEAVY_JOB_BLOCK_START_HOUR=18 and
        # HEAVY_JOB_BLOCK_END_HOUR=23.
        self.HEAVY_JOB_BLOCK_START_HOUR: int = _env_int("HEAVY_JOB_BLOCK_START_HOUR", 0)
        self.HEAVY_JOB_BLOCK_END_HOUR: int = _env_int("HEAVY_JOB_BLOCK_END_HOUR", 0)

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    def validate(self) -> None:
        validate_settings(self)

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
            "Wikidata": self.WIKIDATA_DAILY_LIMIT,
            "GameBrain": self.GAMEBRAIN_DAILY_LIMIT,
            "Groq": self.GROQ_DAILY_LIMIT,
            "Gemini": self.GEMINI_DAILY_LIMIT,
            "CloudflareAI": self.CLOUDFLARE_AI_DAILY_LIMIT,
            "OpenRouter": self.OPENROUTER_DAILY_LIMIT,
            "AI:Similarity": self.SIMILARITY_AI_DAILY_LIMIT,
        }

    def provider_daily_token_limits(self) -> dict[str, int]:
        """source -> daily token ceiling. Absent means requests are the only cap."""
        return {
            "Groq": self.GROQ_DAILY_TOKEN_LIMIT,
            "Gemini": self.GEMINI_DAILY_TOKEN_LIMIT,
            "CloudflareAI": self.CLOUDFLARE_AI_DAILY_TOKEN_LIMIT,
            "OpenRouter": self.OPENROUTER_DAILY_TOKEN_LIMIT,
        }

    def provider_budget_aliases(self) -> dict[str, str]:
        # Metacritic scores are fetched through the RAWG API with the same key,
        # so they must draw from one budget — separate budgets would let combined
        # traffic reach 2x the daily limit.
        return {"Metacritic": "RAWG"}

    def provider_window_limits(self) -> dict[str, list[tuple[str, int, int]]]:
        """source -> [(kind, request_limit, seconds)]"""
        return {
            "OpenCritic": [
                ("rolling", self.OPENCRITIC_PER_SECOND_LIMIT, 1),
            ],
            "RAWG": [("monthly", self.RAWG_MONTHLY_LIMIT, 31 * 24 * 60 * 60)],
            "ITAD": [("rolling", self.ITAD_FIVE_MINUTE_LIMIT, 5 * 60)],
        }

    def provider_window_reset_day(self, source: str, kind: str) -> int:
        if source == "RAWG" and kind == "monthly":
            return self.RAWG_MONTHLY_RESET_DAY
        return 1

    def budget_reserve_percent(self, source: str) -> int:
        if source in {"OpenCritic", OPENCRITIC_SEARCH_SOURCE}:
            # 190/24/3 are already below the 200/25/4 hard limits. Applying the
            # generic reserve again would unnecessarily reduce the free plan.
            return 0
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

    def gemini_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    def cloudflare_ai_configured(self) -> bool:
        return bool(self.CLOUDFLARE_API_TOKEN and self.CLOUDFLARE_ACCOUNT_ID)

    def openrouter_configured(self) -> bool:
        return bool(self.OPENROUTER_API_KEY)

    def ai_configured(self) -> bool:
        checks = {
            "groq": self.groq_configured,
            "gemini": self.gemini_configured,
            "cloudflare": self.cloudflare_ai_configured,
            "openrouter": self.openrouter_configured,
        }
        return any(checks[name]() for name in self.AI_PROVIDER_ORDER)

    def itad_configured(self) -> bool:
        return bool(self.ITAD_API_KEY)

    def steam_configured(self) -> bool:
        return bool(self.STEAM_WEB_API_KEY)

    def wikidata_configured(self) -> bool:
        return True

    def gamebrain_configured(self) -> bool:
        return bool(
            self.GAMEBRAIN_API_KEY
            and self.GAMEBRAIN_NONCOMMERCIAL_ENABLED
            and self.GAMEBRAIN_CACHE_PERMISSION_GRANTED
        )

    def cheapshark_configured(self) -> bool:
        return True  # No key required


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
