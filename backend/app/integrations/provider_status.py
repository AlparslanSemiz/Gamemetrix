import os


def get_provider_statuses() -> list[dict[str, str]]:
    opencritic_ready = bool(os.getenv("OPENCRITIC_API_KEY") or os.getenv("RAPIDAPI_KEY"))
    rawg_ready = bool(os.getenv("RAWG_API_KEY"))
    metacritic_ready = rawg_ready or bool(
        os.getenv("METACRITIC_API_KEY") or os.getenv("METACRITIC_API_BASE")
    )

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
            "status": "ready" if rawg_ready else "needs_credentials",
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
            "status": "ready" if metacritic_ready else "needs_provider",
            "detail": (
                "Metacritic scores are read via RAWG when RAWG_API_KEY is configured; "
                "direct Metacritic requires a licensed provider."
            ),
        },
    ]
