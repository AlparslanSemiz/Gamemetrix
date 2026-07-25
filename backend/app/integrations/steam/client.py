"""Steam Store HTTP surface: endpoints, timeouts, and the shared appdetails fetch.

Every appdetails caller wants the same thing — one app's `data` block, or
nothing — so the request/unwrap dance lives here once.
"""

import re

import httpx

from ..http_retry import DEFAULT_HEADERS
from ..steam_quota import stop_steam_requests_if_rate_limited

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

TIMEOUT_SEARCH = 8
TIMEOUT_REVIEWS = 12
TIMEOUT_DETAILS = 12
TIMEOUT_BULK_DETAILS = 20

STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")


def store_page_url(app_id: int) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"


def extract_steam_app_id(*values: str | None) -> int | None:
    """Last-resort recovery of an app id from a slug or CDN URL.

    Prefer games.steam_app_id — this only guesses from strings that happen to
    embed the id, which fails whenever the cover art does not come from Steam.
    """
    for value in values:
        if not value:
            continue
        match = STEAM_APP_ID_RE.search(value)
        if match:
            return int(match.group(1))
    return None


async def fetch_app_data(
    app_id: int,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: int = TIMEOUT_DETAILS,
    **params: object,
) -> dict | None:
    """One app's appdetails `data` block, or None if Steam has nothing usable.

    Pass `client` to reuse an open connection (the DLC walk does this).
    """
    query = {"appids": app_id, **params}
    if client is not None:
        response = await client.get(APP_DETAILS_URL, params=query, timeout=timeout)
    else:
        async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS) as owned_client:
            response = await owned_client.get(APP_DETAILS_URL, params=query)

    if stop_steam_requests_if_rate_limited(response) or not response.is_success:
        return None
    entry = response.json().get(str(app_id), {})
    if not entry.get("success"):
        return None
    return entry.get("data", {})
