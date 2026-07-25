"""Per-API source overview for the admin panel.

One row per rate-limiter budget bucket, enriched with its registry role, weight,
configured state, today's budget usage, last-used time, and which periodic loop
keeps it fed. Read-only aggregation — the rate limiter, registry, and config are
the sources of truth.
"""

from __future__ import annotations

from ..config import get_settings
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.source_registry import REGISTRY

# Bucket display order: score-critical rating sources first, then support sources.
_ORDER: tuple[str, ...] = (
    "Metacritic",
    "OpenCritic",
    "OpenCritic:search",
    "IGDB",
    "Steam",
    "RAWG",
    "SteamSpy",
    "CheapShark",
    "ITAD",
    "FreeToGame",
    "Wikidata",
    "GameBrain",
    "HLTB",
)

# Which periodic loop(s) keep each bucket fed. Data Fill runs every stage, so it
# touches all of them; the extra labels name the focused loop that also drives it.
_DRIVEN_BY: dict[str, str] = {
    "Metacritic": "Data Fill · Score refresh (via RAWG)",
    "OpenCritic": "Data Fill · Score refresh",
    "OpenCritic:search": "Data Fill · Score refresh",
    "IGDB": "Data Fill · Score refresh · Catalog · Playtime",
    "Steam": "Data Fill · Score refresh · Prices",
    "RAWG": "Data Fill · Score refresh · Metadata",
    "SteamSpy": "Data Fill (catalog)",
    "CheapShark": "Data Fill (catalog · prices · Metacritic seed)",
    "ITAD": "Data Fill (prices)",
    "FreeToGame": "Data Fill (catalog)",
    "Wikidata": "Data Fill · Metadata (exact ID)",
    "GameBrain": "Data Fill · Metadata (optional non-commercial)",
    "HLTB": "Data Fill · HLTB loop",
}

# Bucket -> (provider's real limit note, headroom category).
# headroom = our cap is far below the provider's real limit (safe to raise, free)
# capped   = our cap already sits at the provider's hard ceiling (raising is pointless)
# metered  = raising means paying overage
# window   = constrained by a short rolling window, not a daily cap
# scrape   = no official API; deliberately paced
_PROVIDER_LIMIT: dict[str, tuple[str, str]] = {
    "RAWG": ("20k / month hard cap (free tier)", "capped"),
    "Metacritic": ("via RAWG — shares its 20k/month", "capped"),
    "OpenCritic": ("RapidAPI plan quota — billed on overage", "metered"),
    "OpenCritic:search": ("RapidAPI search quota — billed on overage", "metered"),
    "IGDB": ("~4 req/sec (Twitch), no daily cap", "headroom"),
    "Steam": ("public endpoint, no fixed daily cap", "headroom"),
    "SteamSpy": ("~1 req/sec, no daily cap", "headroom"),
    "CheapShark": ("no auth, generous", "headroom"),
    "ITAD": ("rolling 5-min window", "window"),
    "FreeToGame": ("no auth, generous", "headroom"),
    "Wikidata": ("public SPARQL endpoint; usage-policy paced", "headroom"),
    "GameBrain": ("free plan: 50 tokens/day, non-commercial only", "capped"),
    "HLTB": ("scraped, no official API — keep gentle", "scrape"),
}

_ROLE_BY_TYPE: dict[str, str] = {
    "critic": "Rating · Critic",
    "user": "Rating · Player",
    "aggregate": "Catalog / enrichment",
    "popularity": "Popularity",
    "price": "Price / deals",
    "metadata": "Catalog / metadata",
}

# Buckets that are not registry sources.
_EXTRA_ROLES: dict[str, str] = {
    "HLTB": "Playtime",
    "OpenCritic:search": "Search sub-budget",
    "Wikidata": "Catalog / metadata",
    "GameBrain": "Catalog / metadata",
}


def _configured(bucket: str) -> bool:
    cfg = get_settings()
    if bucket in ("RAWG", "Metacritic"):
        return cfg.rawg_configured()
    if bucket in ("OpenCritic", "OpenCritic:search"):
        return cfg.opencritic_configured()
    if bucket == "IGDB":
        return cfg.igdb_configured()
    if bucket == "ITAD":
        return bool(cfg.ITAD_API_KEY)
    if bucket == "GameBrain":
        return cfg.gamebrain_configured()
    if bucket == "Wikidata":
        return True
    return True  # Steam, SteamSpy, CheapShark, FreeToGame, HLTB need no key


def _role(bucket: str) -> str:
    definition = REGISTRY.get(bucket)
    if definition is not None:
        base = _ROLE_BY_TYPE.get(definition.source_type, definition.source_type)
        return f"{base} (primary)" if definition.is_primary else base
    return _EXTRA_ROLES.get(bucket, "Support")


def _source_entry(bucket: str, budget: dict[str, object]) -> dict[str, object]:
    definition = REGISTRY.get(bucket)
    provider_limit, headroom = _PROVIDER_LIMIT.get(bucket, ("provider default", "window"))
    return {
        "key": bucket,
        "display_name": definition.display_name if definition else bucket,
        "role": _role(bucket),
        "is_rating": bool(definition and definition.is_primary),
        "weight": definition.weight if definition and definition.is_primary else None,
        "requires_pc": bool(definition and definition.requires_pc),
        "configured": _configured(bucket),
        "provider_limit": provider_limit,
        "headroom": headroom,
        "metered": bool(budget.get("metered")),
        "used": budget.get("used", 0),
        "limit": budget.get("limit", 0),
        "usable_limit": budget.get("usable_limit", 0),
        "remaining": budget.get("remaining", 0),
        "reserve_percent": budget.get("reserve_percent", 0),
        "last_used_at": budget.get("updated_at"),
        "windows": budget.get("windows", {}),
        "driven_by": _DRIVEN_BY.get(bucket, "Data Fill"),
    }


def api_sources_status() -> dict[str, object]:
    budgets = get_rate_limiter().status()
    ordered = [key for key in _ORDER if key in budgets]
    ordered += [key for key in sorted(budgets) if key not in _ORDER]
    return {"sources": [_source_entry(key, budgets[key]) for key in ordered]}
