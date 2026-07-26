from ..config import get_settings


def get_provider_statuses() -> list[dict[str, str]]:
    cfg = get_settings()
    opencritic_ready = cfg.opencritic_configured()
    rawg_ready = cfg.rawg_configured()
    metacritic_ready = rawg_ready

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
            "source": "HowLongToBeat",
            "status": "ready",
            "detail": "No authentication required; enriches completion times and can repair missing cover art.",
        },
        {
            "source": "RAWG",
            "status": "ready" if rawg_ready else "needs_credentials",
            "detail": "Provides large game catalogs, descriptions, images, platforms, ratings, and Metacritic fields.",
        },
        {
            "source": "Steam",
            "status": "ready",
            "detail": (
                "Public metadata/reviews are ready; the official full catalog additionally "
                "requires STEAM_WEB_API_KEY."
            ),
        },
        {
            "source": "IGDB",
            "status": "ready" if cfg.igdb_configured() else "needs_credentials",
            "detail": "Requires Twitch OAuth credentials: IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.",
        },
        {
            "source": "Wikidata",
            "status": "ready",
            "detail": "No key required; fills CC0 structured metadata by exact Steam/IGDB identity.",
        },
        {
            "source": "GameBrain",
            "status": "ready" if cfg.gamebrain_configured() else "disabled",
            "detail": (
                "Free plan is non-commercial only and default terms prohibit storage. "
                "Requires a key, non-commercial opt-in, and written cache permission."
            ),
        },
        {
            "source": "Groq",
            "status": "ready" if cfg.groq_configured() else "needs_credentials",
            "detail": (
                "Reviews suspicious catalog rows and generates bounded text under "
                "one shared persistent free-tier budget."
            ),
        },
        {
            "source": "Gemini",
            "status": "ready" if cfg.gemini_configured() else "needs_credentials",
            "detail": "Second AI fallback using the configured stable Flash-Lite model.",
        },
        {
            "source": "Cloudflare Workers AI",
            "status": (
                "ready" if cfg.cloudflare_ai_configured() else "needs_credentials"
            ),
            "detail": "Third AI fallback; requires an account ID and scoped API token.",
        },
        {
            "source": "OpenRouter",
            "status": "ready" if cfg.openrouter_configured() else "needs_credentials",
            "detail": "Final AI fallback, configured to use the free-model router.",
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
