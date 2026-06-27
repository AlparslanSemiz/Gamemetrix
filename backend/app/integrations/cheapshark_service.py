"""
CheapShark service adapter.

CheapShark is the secondary/fallback PC pricing source when ITAD is unavailable.
No API key required. User-Agent set from CHEAPSHARK_USER_AGENT env var.
API docs: https://apidocs.cheapshark.com/
"""

import logging
import time

import httpx

from ..config import get_settings
from .types import NormalizedGame, SourceHealth

log = logging.getLogger(__name__)

CS_BASE = "https://www.cheapshark.com/api/1.0"
SMOKE_TEST_TITLE = "Portal 2"

# CheapShark store IDs (subset of common stores)
STORE_NAMES: dict[str, str] = {
    "1": "Steam",
    "25": "Epic Games Store",
    "8": "GOG",
    "13": "Fanatical",
    "2": "GamersGate",
    "3": "GreenManGaming",
    "27": "GameBillet",
}


class CheapSharkService:
    def is_configured(self) -> bool:
        return True  # No key needed

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": get_settings().CHEAPSHARK_USER_AGENT}

    async def health_check(self) -> SourceHealth:
        try:
            t0 = time.monotonic()
            deals = await self.search_deals(SMOKE_TEST_TITLE, limit=3)
            latency = int((time.monotonic() - t0) * 1000)
            if deals:
                return SourceHealth(
                    source="cheapshark",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f'Search "{SMOKE_TEST_TITLE}" returned {len(deals)} deal(s)',
                    latency_ms=latency,
                )
            return SourceHealth(
                source="cheapshark",
                configured=True,
                working=False,
                status="failing",
                message="CheapShark returned no deals for test title",
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="cheapshark",
                configured=True,
                working=False,
                status="failing",
                message=f"CheapShark request failed: {type(exc).__name__}",
            )

    async def search_deals(self, title: str, limit: int = 10) -> list[dict]:
        """Search deals by title. Returns raw CheapShark deal objects."""
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers()) as client:
                resp = await client.get(
                    f"{CS_BASE}/deals",
                    params={"title": title, "pageSize": limit, "sortBy": "Price"},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("CheapShark search failed for %r: %s", title, exc)
            return []

    async def get_game_deals(self, cs_game_id: str) -> list[dict]:
        """Get all deals for a known CheapShark game ID."""
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers()) as client:
                resp = await client.get(
                    f"{CS_BASE}/deals",
                    params={"id": cs_game_id, "pageSize": 20},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("CheapShark game deals failed for %s: %s", cs_game_id, exc)
            return []

    async def lookup_game_id(self, title: str) -> str | None:
        """Search games endpoint to find the CheapShark game ID."""
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers()) as client:
                resp = await client.get(
                    f"{CS_BASE}/games",
                    params={"title": title, "limit": 3},
                )
                resp.raise_for_status()
                results = resp.json()
                if results:
                    return str(results[0].get("gameID"))
        except Exception as exc:
            log.warning("CheapShark game lookup failed for %r: %s", title, exc)
        return None

    def normalize_deal(self, raw: dict) -> NormalizedGame:
        """Convert one CheapShark deal into a NormalizedGame with price fields."""
        store_id = str(raw.get("storeID", ""))
        store_name = STORE_NAMES.get(store_id, f"Store {store_id}")

        normal_price = float(raw.get("normalPrice", 0)) or None
        sale_price = float(raw.get("salePrice", 0)) or None
        savings = float(raw.get("savings", 0))

        return NormalizedGame(
            source="CheapShark",
            external_id=str(raw.get("dealID", "")),
            name=raw.get("title", ""),
            cover_url=raw.get("thumb"),
            list_price=normal_price,
            sale_price=sale_price,
            currency="USD",
            raw={
                "cs_deal_id": raw.get("dealID"),
                "cs_game_id": raw.get("gameID"),
                "store_id": store_id,
                "store_name": store_name,
                "normal_price": normal_price,
                "sale_price": sale_price,
                "savings_pct": round(savings, 1),
                "deal_rating": raw.get("dealRating"),
                "steam_app_id": raw.get("steamAppID"),
                "metacritic_score": raw.get("metacriticScore"),
                "steam_rating_percent": raw.get("steamRatingPercent"),
                "steam_rating_count": raw.get("steamRatingCount"),
            },
        )


cheapshark_service = CheapSharkService()
