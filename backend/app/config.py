"""
Centralized settings loaded from environment / .env file.
Keys are never exposed outside this module — callers get bool/status, not raw values.
"""

import os


class Settings:
    def __init__(self) -> None:
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
        self.ITAD_API_KEY: str = os.getenv("ITAD_API_KEY", "")
        self.STEAM_WEB_API_KEY: str = os.getenv("STEAM_WEB_API_KEY", "")
        self.CHEAPSHARK_USER_AGENT: str = os.getenv(
            "CHEAPSHARK_USER_AGENT", "GameMetrix/0.1"
        )
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://admin:password123@localhost:5432/gamemetrix",
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

    # ── Configured checks — never return raw key values ─────────────────────

    def igdb_configured(self) -> bool:
        return bool(self.IGDB_CLIENT_ID and self.IGDB_CLIENT_SECRET)

    def rawg_configured(self) -> bool:
        return bool(self.RAWG_API_KEY)

    def opencritic_configured(self) -> bool:
        return bool(self.RAPIDAPI_KEY)

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
