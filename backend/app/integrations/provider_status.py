import os


def get_provider_statuses() -> list[dict[str, str]]:
    opencritic_ready = bool(os.getenv("OPENCRITIC_API_KEY") or os.getenv("OPENCRITIC_API_BASE"))
    metacritic_ready = bool(os.getenv("METACRITIC_API_KEY") or os.getenv("METACRITIC_API_BASE"))

    return [
        {
            "source": "FreeToGame",
            "status": "ready",
            "detail": "No authentication required; imports free-to-play catalog data.",
        },
        {
            "source": "CheapShark",
            "status": "ready",
            "detail": "No authentication required; imports PC deal, store, Metacritic, and Steam rating data.",
        },
        {
            "source": "SteamSpy",
            "status": "ready",
            "detail": "No authentication required; imports broad Steam catalog popularity and review aggregates.",
        },
        {
            "source": "RAWG",
            "status": "ready" if os.getenv("RAWG_API_KEY") else "needs_credentials",
            "detail": "Provides large game catalogs, descriptions, images, platforms, ratings, and Metacritic fields.",
        },
        {
            "source": "Steam",
            "status": "ready",
            "detail": "Uses Steam's public app review summary endpoint.",
        },
        {
            "source": "IGDB",
            "status": "ready" if os.getenv("IGDB_CLIENT_ID") and os.getenv("IGDB_CLIENT_SECRET") else "needs_credentials",
            "detail": "Requires Twitch OAuth credentials: IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.",
        },
        {
            "source": "OpenCritic",
            "status": "ready" if opencritic_ready else "needs_provider",
            "detail": "Configure an approved OpenCritic/RapidAPI/export provider before live calls.",
        },
        {
            "source": "Metacritic",
            "status": "needs_provider" if not metacritic_ready else "ready",
            "detail": "Metacritic has no public official game API; use a licensed provider.",
        },
    ]
