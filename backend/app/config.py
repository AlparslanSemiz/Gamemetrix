"""
Centralized settings loaded from environment / .env file.
Keys are never exposed outside this module — callers get bool/status, not raw values.
"""

import os


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
        self.ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "")
        self.ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "")
        self.PUBLIC_READ_RATE_LIMIT: str = os.getenv("PUBLIC_READ_RATE_LIMIT", "300/minute")
        self.AUTH_RATE_LIMIT: str = os.getenv("AUTH_RATE_LIMIT", "5/minute")
        self.RATE_LIMIT_STORAGE_URI: str = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
        # ── API credentials ──────────────────────────────────────────────────
        self.IGDB_CLIENT_ID: str = os.getenv("IGDB_CLIENT_ID", "")
        self.IGDB_CLIENT_SECRET: str = os.getenv("IGDB_CLIENT_SECRET", "")
        self.RAWG_API_KEY: str = os.getenv("RAWG_API_KEY", "")
        self.OPENCRITIC_API_BASE: str = os.getenv(
            "OPENCRITIC_API_BASE", "https://opencritic-api.p.rapidapi.com/api"
        )
        self.RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
        self.RAPIDAPI_HOST: str = os.getenv(
            "RAPIDAPI_HOST", "opencritic-api.p.rapidapi.com"
        )
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.ITAD_API_KEY: str = os.getenv("ITAD_API_KEY", "")
        self.STEAM_WEB_API_KEY: str = os.getenv("STEAM_WEB_API_KEY", "")
        self.CHEAPSHARK_USER_AGENT: str = os.getenv(
            "CHEAPSHARK_USER_AGENT", "GameMetrix/0.1"
        )
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://admin:password123@localhost:5432/gamemetrix",
        )
        self.CORS_ALLOW_ORIGINS: list[str] = _csv(
            os.getenv(
                "CORS_ALLOW_ORIGINS",
                ",".join(
                    [
                        "http://localhost:5173",
                        "http://127.0.0.1:5173",
                        "http://localhost:5174",
                        "http://127.0.0.1:5174",
                        "http://gamemetrix.me",
                        "https://gamemetrix.me",
                        "http://www.gamemetrix.me",
                        "https://www.gamemetrix.me",
                    ]
                ),
            )
        )
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
        self.OPENCRITIC_DAILY_LIMIT: int = int(os.getenv("OPENCRITIC_DAILY_LIMIT", "4"))
        self.IGDB_DAILY_LIMIT: int = int(os.getenv("IGDB_DAILY_LIMIT", "400"))
        self.RAWG_DAILY_LIMIT: int = int(os.getenv("RAWG_DAILY_LIMIT", "600"))
        self.STEAM_DAILY_LIMIT: int = int(os.getenv("STEAM_DAILY_LIMIT", "300"))
        self.STEAMSPY_DAILY_LIMIT: int = int(os.getenv("STEAMSPY_DAILY_LIMIT", "300"))
        # ── Per-source score weights (relative; default 1.0 = equal) ─────────
        # Higher values increase that source's share of the GameMetrix score.
        # Example: SCORE_WEIGHT_METACRITIC=2 gives Metacritic double influence.
        self.SCORE_WEIGHT_METACRITIC: float = float(os.getenv("SCORE_WEIGHT_METACRITIC", "1.0"))
        self.SCORE_WEIGHT_OPENCRITIC: float = float(os.getenv("SCORE_WEIGHT_OPENCRITIC", "1.0"))
        self.SCORE_WEIGHT_STEAM: float = float(os.getenv("SCORE_WEIGHT_STEAM", "1.0"))
        self.SCORE_WEIGHT_IGDB: float = float(os.getenv("SCORE_WEIGHT_IGDB", "1.0"))
        self.SCORE_WEIGHT_RAWG: float = float(os.getenv("SCORE_WEIGHT_RAWG", "0.7"))
        self.SCORE_WEIGHT_STEAMSPY: float = float(os.getenv("SCORE_WEIGHT_STEAMSPY", "1.0"))
        self.SCORE_WEIGHT_CHEAPSHARK: float = float(os.getenv("SCORE_WEIGHT_CHEAPSHARK", "1.0"))
        self.SCORE_WEIGHT_FREETOGAME: float = float(os.getenv("SCORE_WEIGHT_FREETOGAME", "1.0"))
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
        # ── Heavy admin jobs (imports, refresh-all) — peak-hour block ────────
        # Both 0 (default) disables the block entirely. To pause heavy jobs
        # 18:00-23:00 local time, set HEAVY_JOB_BLOCK_START_HOUR=18 and
        # HEAVY_JOB_BLOCK_END_HOUR=23.
        self.HEAVY_JOB_BLOCK_START_HOUR: int = int(os.getenv("HEAVY_JOB_BLOCK_START_HOUR", "0"))
        self.HEAVY_JOB_BLOCK_END_HOUR: int = int(os.getenv("HEAVY_JOB_BLOCK_END_HOUR", "0"))

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    # ── Configured checks — never return raw key values ─────────────────────

    def igdb_configured(self) -> bool:
        return bool(self.IGDB_CLIENT_ID and self.IGDB_CLIENT_SECRET)

    def rawg_configured(self) -> bool:
        return bool(self.RAWG_API_KEY)

    def opencritic_configured(self) -> bool:
        return bool(self.RAPIDAPI_KEY)

    def anthropic_configured(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)

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
