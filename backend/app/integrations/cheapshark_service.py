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
    "2": "GamersGate",
    "3": "GreenManGaming",
    "4": "Amazon",
    "5": "GameStop",
    "6": "Direct2Drive",
    "7": "GOG",
    "8": "Origin",
    "9": "Get Games",
    "10": "Shiny Loot",
    "11": "Humble Store",
    "12": "Desura",
    "13": "Ubisoft Store",
    "14": "IndieGameStand",
    "15": "Fanatical",
    "16": "Gamesrocket",
    "17": "Games Republic",
    "18": "SilaGames",
    "19": "Playfield",
    "20": "ImperialGames",
    "21": "WinGameStore",
    "22": "FunStockDigital",
    "23": "GameBillet",
    "24": "Voidu",
    "25": "Epic Games Store",
    "26": "Razer Game Store",
    "27": "Gamesplanet",
    "28": "Gamesload",
    "29": "2Game",
    "30": "IndieGala",
    "31": "Blizzard Shop",
    "32": "AllYouPlay",
    "33": "DLGamer",
    "34": "Noctre",
    "35": "DreamGame",
}

_ADDON_TITLE_TERMS = (
    "upgrade",
    "dlc",
    "soundtrack",
    "bundle",
    "pack",
    "season pass",
    "expansion",
)


def _normalize_title(value: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
    )


def _looks_like_addon(title: str) -> bool:
    normalized = _normalize_title(title)
    return any(term in normalized for term in _ADDON_TITLE_TERMS)


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
                    f"{CS_BASE}/games",
                    params={"id": cs_game_id},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            log.warning("CheapShark game deals failed for %s: %s", cs_game_id, exc)
            return []

        info = payload.get("info") or {}
        game_title = info.get("title") or ""
        steam_app_id = info.get("steamAppID")
        deals: list[dict] = []
        for deal in payload.get("deals") or []:
            if not isinstance(deal, dict):
                continue
            deals.append({
                **deal,
                "title": game_title,
                "gameID": cs_game_id,
                "steamAppID": steam_app_id,
                "salePrice": deal.get("price"),
                "normalPrice": deal.get("retailPrice"),
            })
        return deals

    async def lookup_game_id(self, title: str, steam_appid: int | None = None) -> str | None:
        """Search games endpoint to find the CheapShark game ID."""
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers()) as client:
                resp = await client.get(
                    f"{CS_BASE}/games",
                    params={"title": title, "limit": 10},
                )
                resp.raise_for_status()
                results = resp.json()
        except Exception as exc:
            log.warning("CheapShark game lookup failed for %r: %s", title, exc)
            return None

        expected = _normalize_title(title)
        best_id: str | None = None
        for result in results:
            if not isinstance(result, dict):
                continue
            external = str(result.get("external") or "")
            if not external or _looks_like_addon(external):
                continue
            result_appid = str(result.get("steamAppID") or "")
            if steam_appid and result_appid == str(steam_appid):
                return str(result.get("gameID"))
            if _normalize_title(external) == expected and best_id is None:
                best_id = str(result.get("gameID"))
        return best_id

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
