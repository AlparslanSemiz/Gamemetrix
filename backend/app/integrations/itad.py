"""
IsThereAnyDeal (ITAD) integration.

API docs: https://docs.isthereanydeal.com/
Requires ITAD_API_KEY in .env (free registration at isthereanydeal.com/dev/app/).

Endpoint summary:
  GET  /games/lookup/v1              title → itad_id (plain)
  GET  /games/prices/v3              itad_id(s) → current store prices
  GET  /games/historylow/v1          itad_id(s) → all-time historical low
  GET  /games/subscriptions/v1       itad_id(s) → included in which services
"""

import logging
import os
from datetime import UTC, datetime, date

import httpx

from .value_score import PriceData, calculate_value_score  # noqa: F401 – re-exported

log = logging.getLogger(__name__)

ITAD_API_BASE = "https://api.isthereanydeal.com"
ITAD_API_KEY = os.getenv("ITAD_API_KEY", "")


def _headers() -> dict[str, str]:
    return {"ITAD-API-Key": ITAD_API_KEY}


async def lookup_itad_id(title: str) -> str | None:
    """Resolve a game title to its ITAD plain (internal game ID)."""
    if not ITAD_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ITAD_API_BASE}/games/lookup/v1",
                headers=_headers(),
                params={"title": title},
            )
            resp.raise_for_status()
            data = resp.json()
            # Response: { "game": { "id": "...", "slug": "...", "title": "..." }, "found": true }
            if data.get("found") and isinstance(data.get("game"), dict):
                return str(data["game"]["id"])
    except Exception as exc:
        log.debug("ITAD lookup failed for %r: %s", title, exc)
    return None


async def get_current_prices(itad_id: str, country: str = "US") -> list[dict]:
    """
    Return current storefront prices for a game.

    Each item: { store, store_name, url, price_new, price_old, price_cut,
                 currency, is_drm_free, platforms }
    """
    if not ITAD_API_KEY or not itad_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ITAD_API_BASE}/games/prices/v3",
                headers=_headers(),
                params={"id": itad_id, "country": country, "capacity": 20},
            )
            resp.raise_for_status()
            results = resp.json()
            # Response: list of { id, deals: [{ shop, price, regular, cut, ... }] }
            for entry in results:
                if str(entry.get("id")) == itad_id:
                    return entry.get("deals", [])
    except Exception as exc:
        log.debug("ITAD prices failed for %s: %s", itad_id, exc)
    return []


async def get_historical_low(itad_id: str, country: str = "US") -> dict | None:
    """
    Return the all-time historical low price for a game.

    Returns: { price, cut, shop, recorded } or None.
    """
    if not ITAD_API_KEY or not itad_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ITAD_API_BASE}/games/historylow/v1",
                headers=_headers(),
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


async def get_subscription_info(itad_id: str) -> list[str]:
    """Return names of subscription services that currently include the game."""
    if not ITAD_API_KEY or not itad_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ITAD_API_BASE}/games/subscriptions/v1",
                headers=_headers(),
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
    title: str,
    country: str = "US",
) -> "PriceData | None":
    """
    One-call helper: resolve title → ITAD ID → PriceData.

    Returns None when the key is missing or no data is found.
    """
    itad_id = await lookup_itad_id(title)
    if not itad_id:
        return None

    deals, low_entry, subs = await _gather_price_details(itad_id, country)

    if not deals and not low_entry:
        return None

    # Pick the best current deal (lowest sale price)
    best_deal: dict = {}
    if deals:
        best_deal = min(deals, key=lambda d: float(d.get("price", {}).get("amount", 9999)))

    list_price: float | None = None
    sale_price: float | None = None
    discount_pct: int | None = None
    store: str = best_deal.get("shop", {}).get("name", "") if best_deal else ""
    currency: str = best_deal.get("price", {}).get("currency", "USD") if best_deal else "USD"

    if best_deal:
        sale_price = float(best_deal.get("price", {}).get("amount", 0)) or None
        list_price = float(best_deal.get("regular", {}).get("amount", 0)) or sale_price
        discount_pct = int(best_deal.get("cut", 0)) or None

    historical_low: float | None = None
    historical_low_date: date | None = None
    if low_entry:
        historical_low = float(low_entry.get("price", {}).get("amount", 0)) or None
        raw_date = low_entry.get("recorded")
        if raw_date:
            try:
                historical_low_date = datetime.fromisoformat(raw_date).date()
            except ValueError:
                pass

    is_free = sale_price == 0.0 if sale_price is not None else False
    is_sub_included = len(subs) > 0
    sub_service = subs[0] if subs else None

    return PriceData(
        store=store,
        currency=currency,
        list_price=list_price,
        sale_price=sale_price if not is_free else None,
        discount_percent=discount_pct,
        historical_low=historical_low,
        historical_low_date=historical_low_date,
        is_free=is_free,
        is_subscription_included=is_sub_included,
        subscription_service=sub_service,
        itad_id=itad_id,
        fetched_at=datetime.now(UTC),
        source="ITAD",
    )


async def _gather_price_details(
    itad_id: str,
    country: str,
) -> tuple[list[dict], dict | None, list[str]]:
    import asyncio
    deals, low_entry, subs = await asyncio.gather(
        get_current_prices(itad_id, country),
        get_historical_low(itad_id, country),
        get_subscription_info(itad_id),
    )
    return deals, low_entry, subs
