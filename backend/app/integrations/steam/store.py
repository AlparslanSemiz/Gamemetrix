"""Store-page data: screenshots, requirements, website, price, DLC, release dates."""

from datetime import date

import httpx

from ..http_retry import DEFAULT_HEADERS
from ..types import bounded_int
from .client import (
    APP_DETAILS_URL,
    TIMEOUT_BULK_DETAILS,
    TIMEOUT_DETAILS,
    fetch_app_data,
    store_page_url,
)
from .parsing import clean_requirement_block, clean_website_url, parse_release_date

MAX_SCREENSHOTS = 16
MAX_DLCS = 24
_MAX_PRICE_CENTS = 100_000_000
_CENTS_PER_UNIT = 100
_DEFAULT_CURRENCY = "USD"
_CURRENCY_CODE_LENGTH = 3

_REQUIREMENT_PLATFORMS = (
    ("pc_requirements", "PC"),
    ("mac_requirements", "Mac"),
    ("linux_requirements", "Linux"),
)


async def fetch_steam_screenshots(app_id: int) -> list[str]:
    """Up to MAX_SCREENSHOTS full-resolution screenshot URLs for a Steam app."""
    data = await fetch_app_data(app_id, filters="screenshots", cc="us")
    if data is None:
        return []
    return [
        shot["path_full"]
        for shot in (data.get("screenshots") or [])
        if isinstance(shot, dict) and shot.get("path_full")
    ][:MAX_SCREENSHOTS]


async def fetch_steam_system_requirements(app_id: int) -> list[dict]:
    """Steam's published system requirements as plain text."""
    data = await fetch_app_data(app_id, cc="us", l="english")
    if data is None:
        return []

    result: list[dict] = []
    for key, platform in _REQUIREMENT_PLATFORMS:
        block = _requirement_block(data.get(key))
        if block is None:
            continue
        minimum, recommended = block
        if minimum or recommended:
            result.append({"platform": platform, "minimum": minimum, "recommended": recommended})
    return result


def _requirement_block(raw: object) -> tuple[str, str] | None:
    if isinstance(raw, str):
        return clean_requirement_block(raw), ""
    if isinstance(raw, dict):
        return clean_requirement_block(raw.get("minimum")), clean_requirement_block(raw.get("recommended"))
    return None


async def fetch_steam_website(app_id: int) -> str | None:
    """The official website listed on Steam, when one is published."""
    data = await fetch_app_data(app_id, filters="basic", cc="us", l="english")
    return clean_website_url(data.get("website")) if data is not None else None


async def fetch_steam_price(app_id: int, country: str = "US") -> dict | None:
    """Official Steam store price data for one app."""
    data = await fetch_app_data(app_id, cc=country.lower(), l="english")
    if data is None:
        return None
    if data.get("is_free"):
        return _free_price(app_id)

    price = data.get("price_overview") or {}
    return _paid_price(app_id, price) if price else None


def _free_price(app_id: int) -> dict:
    return {
        "store": "Steam",
        "currency": _DEFAULT_CURRENCY,
        "list_price": 0.0,
        "sale_price": 0.0,
        "discount_percent": 0,
        "is_free": True,
        "url": store_page_url(app_id),
        "raw": {"steam_app_id": app_id, "is_free": True},
    }


def _paid_price(app_id: int, price: dict) -> dict | None:
    initial = bounded_int(price.get("initial"), maximum=_MAX_PRICE_CENTS)
    final = bounded_int(price.get("final"), maximum=_MAX_PRICE_CENTS)
    if initial is None and final is None:
        return None

    list_price = (
        (initial / _CENTS_PER_UNIT)
        if initial is not None
        else (final / _CENTS_PER_UNIT if final is not None else None)
    )
    sale_price = (final / _CENTS_PER_UNIT) if final is not None else list_price
    if list_price is not None and sale_price is not None and sale_price > list_price:
        list_price = sale_price

    discount_percent = bounded_int(price.get("discount_percent"), maximum=100) or 0
    if list_price and sale_price is not None:
        discount_percent = round(max(0.0, (list_price - sale_price) / list_price) * 100)

    return {
        "store": "Steam",
        "currency": _currency_code(price.get("currency")),
        "list_price": list_price,
        "sale_price": sale_price,
        "discount_percent": discount_percent,
        "is_free": False,
        "url": store_page_url(app_id),
        "raw": {"steam_app_id": app_id, "price_overview": price},
    }


def _currency_code(value: object) -> str:
    currency = str(value or _DEFAULT_CURRENCY).upper()
    if len(currency) != _CURRENCY_CODE_LENGTH or not currency.isalpha():
        return _DEFAULT_CURRENCY
    return currency


async def fetch_steam_dlcs(app_id: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT_DETAILS, headers=DEFAULT_HEADERS) as client:
        data = await fetch_app_data(app_id, client=client, cc="us")
        if data is None:
            return []
        dlc_ids = [int(item) for item in (data.get("dlc") or []) if str(item).isdigit()]

        dlcs: list[dict] = []
        for dlc_id in dlc_ids[:MAX_DLCS]:
            entry = await fetch_app_data(dlc_id, client=client, filters="basic")
            if entry is None or not entry.get("name"):
                continue
            dlcs.append(_dlc_entry(dlc_id, entry))
        return dlcs


def _dlc_entry(dlc_id: int, data: dict) -> dict:
    release = parse_release_date((data.get("release_date") or {}).get("date"))
    return {
        "id": dlc_id,
        "title": data.get("name"),
        "slug": str(dlc_id),
        "release_date": release.isoformat() if release else None,
        "release_year": release.year if release else None,
        "cover_url": data.get("header_image") or "",
        "url": store_page_url(dlc_id),
        "type": data.get("type") or "dlc",
    }


async def get_steam_release_date(app_id: int) -> date | None:
    data = await fetch_app_data(app_id, filters="release_date", cc="us")
    if data is None:
        return None
    return parse_release_date(data.get("release_date", {}).get("date"))


async def get_steam_release_dates(app_ids: list[int]) -> dict[int, date]:
    if not app_ids:
        return {}

    async with httpx.AsyncClient(timeout=TIMEOUT_BULK_DETAILS, headers=DEFAULT_HEADERS) as client:
        response = await client.get(
            APP_DETAILS_URL,
            params={"appids": ",".join(str(i) for i in app_ids), "filters": "release_date"},
        )
        if not response.is_success:
            return {}

    payload = response.json()
    result: dict[int, date] = {}
    for app_id in app_ids:
        entry = payload.get(str(app_id), {})
        if not entry.get("success"):
            continue
        parsed = parse_release_date(entry.get("data", {}).get("release_date", {}).get("date"))
        if parsed:
            result[app_id] = parsed
    return result
