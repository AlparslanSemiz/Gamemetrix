"""Steam Store HTTP surface: endpoints, timeouts, and the shared appdetails fetch.

Every appdetails caller wants the same thing — one app's `data` block, or
nothing — so the request/unwrap dance lives here once.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

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

# Only URLs that explicitly name a Steam app. A bare trailing number in a slug
# ("year-walk-730") is a RAWG/IGDB id, never a Steam id; the old pattern also
# accepted a trailing "-123" and attached the wrong store page to those games.
STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/)(\d{3,})(?:/|$)")


def store_page_url(app_id: int) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"


def extract_steam_app_id(*values: str | None) -> int | None:
    """Last-resort recovery of an app id from a Steam store/CDN URL.

    Prefer `resolve_steam_app_id` (games.steam_app_id first). Slugs are never a
    source: their numeric suffix is a RAWG/IGDB id.
    """
    for value in values:
        if not value:
            continue
        match = STEAM_APP_ID_RE.search(value)
        if match:
            return int(match.group(1))
    return None


def resolve_steam_app_id(
    game: object,
    external_ids: Mapping[str, str] | None = None,
) -> int | None:
    """The one place that decides which Steam app a game is.

    Order: the stored `games.steam_app_id` (verified or not, it is the id the rest
    of the catalog already agrees on), then a trusted Steam external id, then a
    Steam URL in the artwork. Never the slug. Scores, prices, links and metadata
    all call this so they can no longer disagree about the app.
    """
    stored = getattr(game, "steam_app_id", None)
    if isinstance(stored, int) and stored > 0:
        return stored
    external = (external_ids or {}).get("Steam", "")
    if external.isdigit() and int(external) > 0:
        return int(external)
    return extract_steam_app_id(
        getattr(game, "cover_url", None), getattr(game, "image_url", None)
    )


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


@dataclass(frozen=True)
class AppdetailsOutcome:
    """What one appdetails call told us. `error` means "ask again later", never "wrong id"."""

    status: Literal["ok", "removed", "error"]
    data: dict | None = None


async def fetch_app_outcome(app_id: int, client: httpx.AsyncClient) -> AppdetailsOutcome:
    """Like `fetch_app_data`, but separates "Steam has no such app" from outages and 429s."""
    try:
        response = await client.get(
            APP_DETAILS_URL,
            params={"appids": app_id, "cc": "us", "l": "english"},
            timeout=TIMEOUT_DETAILS,
        )
    except httpx.HTTPError:
        return AppdetailsOutcome("error")
    if stop_steam_requests_if_rate_limited(response) or not response.is_success:
        return AppdetailsOutcome("error")
    try:
        entry = response.json().get(str(app_id), {})
    except ValueError:
        return AppdetailsOutcome("error")
    if not entry.get("success"):
        return AppdetailsOutcome("removed")
    data = entry.get("data")
    return AppdetailsOutcome("ok", data if isinstance(data, dict) else {})
