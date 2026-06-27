"""
IsThereAnyDeal (ITAD) service adapter.

ITAD is the primary PC pricing source.
API docs: https://docs.isthereanydeal.com/
Key passed as Authorization Bearer header (not query param).
Default region: EU / EUR.
"""

import logging
import time
from datetime import UTC, date, datetime

import httpx

from ..config import get_settings
from .types import NormalizedGame, SourceHealth
from .value_score import PriceData

log = logging.getLogger(__name__)

ITAD_BASE = "https://api.isthereanydeal.com"
SMOKE_TEST_TITLE = "Hades"
SMOKE_TEST_TITLES = ["Hades", "Portal 2", "Celeste", "Elden Ring", "Baldur's Gate 3"]


def _auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().ITAD_API_KEY}"}


class ITADService:
    def is_configured(self) -> bool:
        return get_settings().itad_configured()

    async def health_check(self) -> SourceHealth:
        if not self.is_configured():
            return SourceHealth(
                source="itad",
                configured=False,
                working=False,
                status="missing",
                message="ITAD_API_KEY not configured",
            )
        try:
            t0 = time.monotonic()
            itad_id = await self.lookup_id(SMOKE_TEST_TITLE)
            latency = int((time.monotonic() - t0) * 1000)
            if itad_id:
                return SourceHealth(
                    source="itad",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f'Resolved "{SMOKE_TEST_TITLE}" → id={itad_id}',
                    latency_ms=latency,
                )
            return SourceHealth(
                source="itad",
                configured=True,
                working=False,
                status="failing",
                message=f'Could not resolve "{SMOKE_TEST_TITLE}" — check API key or title spelling',
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="itad",
                configured=True,
                working=False,
                status="failing",
                message=f"ITAD request failed: {type(exc).__name__}",
            )

    async def lookup_id(self, title: str) -> str | None:
        """POST /games/lookup/v1 — resolve title to ITAD game UUID."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ITAD_BASE}/games/lookup/v1",
                    headers=_auth_header(),
                    json={"title": title},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("found") and isinstance(data.get("game"), dict):
                    return str(data["game"]["id"])
        except Exception as exc:
            log.debug("ITAD lookup failed for %r: %s", title, exc)
        return None

    async def lookup_by_steam_appid(self, app_id: int) -> str | None:
        """Use ITAD's shops endpoint to find by Steam app ID (shop=steam, shop_game_id=<appid>)."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/overview/v2",
                    headers=_auth_header(),
                    params={"shops": "61", "steam_appid": app_id},  # shop 61 = Steam
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    return str(data[0].get("id"))
        except Exception as exc:
            log.debug("ITAD steam appid lookup failed for %d: %s", app_id, exc)
        return None

    async def get_prices(self, itad_id: str, country: str = "EU") -> list[dict]:
        """GET /games/prices/v3 — current store prices."""
        if not self.is_configured() or not itad_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/prices/v3",
                    headers=_auth_header(),
                    params={"id": itad_id, "country": country, "capacity": 20},
                )
                resp.raise_for_status()
                results = resp.json()
                for entry in results:
                    if str(entry.get("id")) == itad_id:
                        return entry.get("deals", [])
        except Exception as exc:
            log.debug("ITAD prices failed for %s: %s", itad_id, exc)
        return []

    async def get_history_low(self, itad_id: str, country: str = "EU") -> dict | None:
        """GET /games/historylow/v1 — all-time lowest price."""
        if not self.is_configured() or not itad_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/historylow/v1",
                    headers=_auth_header(),
                    params={"id": itad_id, "country": country},
                )
                resp.raise_for_status()
                results = resp.json()
                for entry in results:
                    if str(entry.get("id")) == itad_id and entry.get("low"):
                        return entry["low"]
        except Exception as exc:
            log.debug("ITAD history low failed for %s: %s", itad_id, exc)
        return None

    async def get_subscriptions(self, itad_id: str) -> list[str]:
        """GET /games/subscriptions/v1 — which subscription services include the game."""
        if not self.is_configured() or not itad_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/subscriptions/v1",
                    headers=_auth_header(),
                    params={"id": itad_id},
                )
                resp.raise_for_status()
                results = resp.json()
                for entry in results:
                    if str(entry.get("id")) == itad_id:
                        return [s.get("name", "") for s in entry.get("subscriptions", [])]
        except Exception as exc:
            log.debug("ITAD subscriptions failed for %s: %s", itad_id, exc)
        return []

    async def fetch_price_data(
        self,
        title: str,
        country: str = "EU",
        steam_appid: int | None = None,
    ) -> PriceData | None:
        """Full pipeline: title → ITAD ID → prices + history + subscriptions → PriceData."""
        itad_id = await self.lookup_id(title)
        if not itad_id and steam_appid:
            itad_id = await self.lookup_by_steam_appid(steam_appid)
        if not itad_id:
            return None

        import asyncio
        deals, low, subs = await asyncio.gather(
            self.get_prices(itad_id, country),
            self.get_history_low(itad_id, country),
            self.get_subscriptions(itad_id),
        )

        if not deals and not low:
            return None

        best: dict = {}
        if deals:
            best = min(deals, key=lambda d: float((d.get("price") or {}).get("amount", 9999)))

        list_price: float | None = None
        sale_price: float | None = None
        discount_pct: int | None = None
        store: str = (best.get("shop") or {}).get("name", "") if best else ""
        currency: str = (best.get("price") or {}).get("currency", "EUR") if best else "EUR"

        if best:
            raw_sale = (best.get("price") or {}).get("amount")
            raw_list = (best.get("regular") or {}).get("amount")
            sale_price = float(raw_sale) if raw_sale is not None else None
            list_price = float(raw_list) if raw_list is not None else sale_price
            discount_pct = int(best.get("cut", 0)) or None

        hist_low: float | None = None
        hist_low_date: date | None = None
        if low:
            raw_low = (low.get("price") or {}).get("amount")
            hist_low = float(raw_low) if raw_low is not None else None
            raw_date = low.get("recorded")
            if raw_date:
                try:
                    hist_low_date = datetime.fromisoformat(raw_date).date()
                except ValueError:
                    pass

        is_free = sale_price == 0.0 if sale_price is not None else False
        is_sub = len(subs) > 0

        return PriceData(
            store=store,
            currency=currency,
            list_price=list_price,
            sale_price=sale_price if not is_free else None,
            discount_percent=discount_pct,
            historical_low=hist_low,
            historical_low_date=hist_low_date,
            is_free=is_free,
            is_subscription_included=is_sub,
            subscription_service=subs[0] if subs else None,
            itad_id=itad_id,
            fetched_at=datetime.now(UTC),
            source="ITAD",
        )

    def normalize_for_external_id(self, itad_id: str, title: str) -> NormalizedGame:
        return NormalizedGame(
            source="ITAD",
            external_id=itad_id,
            name=title,
            raw={"itad_id": itad_id},
        )


itad_service = ITADService()
