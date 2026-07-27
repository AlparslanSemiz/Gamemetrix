"""
IsThereAnyDeal (ITAD) service adapter.

ITAD is the primary PC pricing source.
API docs: https://docs.isthereanydeal.com/
Key passed with the current ITAD-API-Key header.
Default region: EU / EUR.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from ..config import get_settings
from .rate_limiter import get_rate_limiter
from .title_matching import titles_match
from .types import NormalizedGame, SourceHealth, bounded_float, bounded_int
from .value_score import PriceData

log = logging.getLogger(__name__)

ITAD_BASE = "https://api.isthereanydeal.com"
DEFAULT_ITAD_COUNTRY = "DE"
SMOKE_TEST_TITLE = "Hades"
SMOKE_TEST_TITLES = ["Hades", "Portal 2", "Celeste", "Elden Ring", "Baldur's Gate 3"]
_MAX_DEAL_URL_LENGTH = 500  # PriceSnapshot.url column width
_AUTH_FAILURE_CODES = frozenset({401, 403})


def _auth_header() -> dict[str, str]:
    return {"ITAD-API-Key": get_settings().ITAD_API_KEY}


def _country_code(country: str) -> str:
    normalized = (country or "").strip().upper()
    return normalized if len(normalized) == 2 and normalized.isalpha() else DEFAULT_ITAD_COUNTRY


def _verified_id(game: dict, expected_title: str) -> str | None:
    """ITAD's lookup is fuzzy, so an unverified hit stores another game's price."""
    matched_title = game.get("title")
    if not titles_match(expected_title, matched_title if isinstance(matched_title, str) else None):
        log.info("ITAD lookup rejected: %r matched %r", expected_title, matched_title)
        return None
    return str(game["id"])


def _log_failure(operation: str, subject: str, exc: Exception) -> None:
    """A swallowed ITAD error is indistinguishable from 'no deals' — say which it was."""
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    if status in _AUTH_FAILURE_CODES:
        log.error("ITAD key rejected on %s (HTTP %s)", operation, status)
        return
    log.warning("ITAD %s failed for %s: %s", operation, subject, exc)


@dataclass(frozen=True)
class _DealSummary:
    store: str
    currency: str
    list_price: float | None
    sale_price: float | None
    discount_percent: int | None
    url: str | None


def _best_deal_summary(deals: list[dict]) -> _DealSummary:
    priced_deals: list[tuple[dict, float]] = []
    for deal in deals:
        price = deal.get("price")
        amount = bounded_float(
            price.get("amount") if isinstance(price, dict) else None,
            maximum=1_000_000.0,
        )
        if amount is not None:
            priced_deals.append((deal, amount))
    best, sale_price = (
        min(priced_deals, key=lambda item: item[1])
        if priced_deals
        else ({}, None)
    )
    shop = best.get("shop") if best else None
    store = str(shop.get("name") or "")[:120] if isinstance(shop, dict) else ""
    price_block = best.get("price") if best else None
    raw_currency = price_block.get("currency") if isinstance(price_block, dict) else None
    currency = str(raw_currency or "EUR").upper()
    if len(currency) != 3 or not currency.isalpha():
        currency = "EUR"

    regular = best.get("regular") if best else None
    list_price = bounded_float(
        regular.get("amount") if isinstance(regular, dict) else None,
        maximum=1_000_000.0,
    )
    list_price = list_price if list_price is not None else sale_price
    if sale_price is not None and list_price is not None and sale_price > list_price:
        list_price = sale_price
    discount_percent = bounded_int(best.get("cut"), maximum=100) if best else None
    if list_price and sale_price is not None:
        discount_percent = round(max(0.0, (list_price - sale_price) / list_price) * 100)
    if not discount_percent:
        discount_percent = None
    return _DealSummary(
        store,
        currency,
        list_price,
        sale_price,
        discount_percent,
        _deal_url(best.get("url") if best else None),
    )


def _deal_url(raw: object) -> str | None:
    """ITAD's terms forbid altering supplied URLs — keep it verbatim or drop it."""
    if not isinstance(raw, str) or not raw:
        return None
    return raw if len(raw) <= _MAX_DEAL_URL_LENGTH else None


def _history_low(low: dict | None) -> tuple[float | None, date | None]:
    if not low:
        return None, None
    low_price = low.get("price")
    amount = bounded_float(
        low_price.get("amount") if isinstance(low_price, dict) else None,
        maximum=1_000_000.0,
    )
    raw_date = low.get("timestamp") or low.get("recorded")
    if not raw_date:
        return amount, None
    try:
        return amount, datetime.fromisoformat(str(raw_date)).date()
    except (TypeError, ValueError):
        return amount, None


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
        t0 = time.monotonic()
        if not await get_rate_limiter().acquire("ITAD"):
            return SourceHealth(
                source="itad",
                configured=True,
                working=False,
                status="rate_limited",
                message="Configured ITAD request budget is exhausted",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{ITAD_BASE}/games/lookup/v1",
                    headers=_auth_header(),
                    params={"title": SMOKE_TEST_TITLE},
                )
            latency = int((time.monotonic() - t0) * 1000)
            if response.status_code in {401, 403}:
                return SourceHealth(
                    source="itad",
                    configured=True,
                    working=False,
                    status="invalid_key",
                    message=f"ITAD API key is invalid or expired (HTTP {response.status_code})",
                    latency_ms=latency,
                )
            if response.status_code == 429:
                return SourceHealth(
                    source="itad", configured=True, working=False,
                    status="rate_limited", message="ITAD quota or rate limit reached (HTTP 429)",
                    latency_ms=latency,
                )
            if not response.is_success:
                return SourceHealth(
                    source="itad",
                    configured=True,
                    working=False,
                    status="provider_error" if response.status_code >= 500 else "failing",
                    message=f"ITAD endpoint returned HTTP {response.status_code}",
                    latency_ms=latency,
                )
            data = response.json()
            itad_id = (
                str(data["game"]["id"])
                if data.get("found") and isinstance(data.get("game"), dict)
                else None
            )
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
        except httpx.TimeoutException:
            return SourceHealth(
                source="itad", configured=True, working=False,
                status="timeout", message="ITAD health check timed out",
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
        """GET /games/lookup/v1 — resolve title to ITAD game UUID."""
        if not self.is_configured():
            return None
        if not await get_rate_limiter().acquire("ITAD"):
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/lookup/v1",
                    headers=_auth_header(),
                    params={"title": title},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("found") and isinstance(data.get("game"), dict):
                    return _verified_id(data["game"], title)
        except Exception as exc:
            _log_failure("lookup", repr(title), exc)
        return None

    async def lookup_by_steam_appid(self, app_id: int) -> str | None:
        """Resolve an ITAD game UUID from a Steam app ID."""
        if not self.is_configured():
            return None
        if not await get_rate_limiter().acquire("ITAD"):
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ITAD_BASE}/games/lookup/v1",
                    headers=_auth_header(),
                    params={"appid": app_id},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("found") and isinstance(data.get("game"), dict):
                    return str(data["game"]["id"])
        except Exception as exc:
            _log_failure("steam appid lookup", str(app_id), exc)
        return None

    async def get_prices(
        self,
        itad_id: str,
        country: str = DEFAULT_ITAD_COUNTRY,
    ) -> list[dict]:
        """POST /games/prices/v3 — current store prices."""
        if not self.is_configured() or not itad_id:
            return []
        if not await get_rate_limiter().acquire("ITAD"):
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ITAD_BASE}/games/prices/v3",
                    headers=_auth_header(),
                    params={"country": _country_code(country), "capacity": 20},
                    json=[itad_id],
                )
                resp.raise_for_status()
            results = resp.json()
            if not isinstance(results, list):
                return []
            for entry in results:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("id")) == itad_id:
                    deals = entry.get("deals", [])
                    return [deal for deal in deals if isinstance(deal, dict)] if isinstance(deals, list) else []
        except Exception as exc:
            _log_failure("prices", itad_id, exc)
        return []

    async def get_history_low(
        self,
        itad_id: str,
        country: str = DEFAULT_ITAD_COUNTRY,
    ) -> dict | None:
        """POST /games/historylow/v1 — all-time lowest price."""
        if not self.is_configured() or not itad_id:
            return None
        if not await get_rate_limiter().acquire("ITAD"):
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ITAD_BASE}/games/historylow/v1",
                    headers=_auth_header(),
                    params={"country": _country_code(country)},
                    json=[itad_id],
                )
                resp.raise_for_status()
            results = resp.json()
            if not isinstance(results, list):
                return None
            for entry in results:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("id")) == itad_id and entry.get("low"):
                    return entry["low"] if isinstance(entry["low"], dict) else None
        except Exception as exc:
            _log_failure("history low", itad_id, exc)
        return None

    async def get_subscriptions(self, itad_id: str) -> list[str]:
        """POST /games/subs/v1 — which subscription services include the game."""
        if not self.is_configured() or not itad_id:
            return []
        if not await get_rate_limiter().acquire("ITAD"):
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ITAD_BASE}/games/subs/v1",
                    headers=_auth_header(),
                    json=[itad_id],
                )
                resp.raise_for_status()
            results = resp.json()
            if not isinstance(results, list):
                return []
            for entry in results:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("id")) == itad_id:
                    subscriptions = entry.get("subs", [])
                    if not isinstance(subscriptions, list):
                        return []
                    return [
                        str(subscription["name"])[:120]
                        for subscription in subscriptions
                        if isinstance(subscription, dict) and subscription.get("name")
                    ]
        except Exception as exc:
            _log_failure("subscriptions", itad_id, exc)
        return []

    async def fetch_price_data(
        self,
        title: str,
        country: str = DEFAULT_ITAD_COUNTRY,
        steam_appid: int | None = None,
    ) -> PriceData | None:
        """Full pipeline: title → ITAD ID → prices + history + subscriptions → PriceData."""
        itad_id = await self.lookup_id(title)
        if not itad_id and steam_appid:
            itad_id = await self.lookup_by_steam_appid(steam_appid)
        if not itad_id:
            return None

        deals, low, subs = await asyncio.gather(
            self.get_prices(itad_id, country),
            self.get_history_low(itad_id, country),
            self.get_subscriptions(itad_id),
        )

        if not deals and not low:
            return None

        deal = _best_deal_summary(deals)
        hist_low, hist_low_date = _history_low(low)
        is_free = deal.sale_price == 0.0 if deal.sale_price is not None else False
        is_sub = len(subs) > 0

        return PriceData(
            store=deal.store,
            currency=deal.currency,
            list_price=deal.list_price,
            sale_price=deal.sale_price if not is_free else None,
            discount_percent=deal.discount_percent,
            historical_low=hist_low,
            historical_low_date=hist_low_date,
            is_free=is_free,
            is_subscription_included=is_sub,
            subscription_service=subs[0] if subs else None,
            itad_id=itad_id,
            fetched_at=datetime.now(UTC),
            source="ITAD",
            url=deal.url,
        )

    def normalize_for_external_id(self, itad_id: str, title: str) -> NormalizedGame:
        return NormalizedGame(
            source="ITAD",
            external_id=itad_id,
            name=title,
            raw={"itad_id": itad_id},
        )


itad_service = ITADService()
