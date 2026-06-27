import logging
import re
from datetime import date, datetime

import httpx

from .types import ExternalScore


log = logging.getLogger(__name__)

_STEAM_STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
_STEAM_APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
_STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

_TIMEOUT_SEARCH = 8
_TIMEOUT_REVIEWS = 12
_TIMEOUT_DETAILS = 12
_TIMEOUT_BULK_DETAILS = 20

# Minimum score floors mapped from Steam's qualitative review summary labels.
_REVIEW_LABEL_FLOORS: dict[str, float] = {
    "overwhelmingly positive": 95.0,
    "very positive": 80.0,
    "mostly positive": 70.0,
    "positive": 70.0,
}

# Known App IDs for seeded games — avoids a title-search round-trip.
STEAM_APP_IDS: dict[str, int] = {
    "baldurs-gate-3": 1086940,
    "elden-ring": 1245620,
    "hades": 1145360,
    "disco-elysium-the-final-cut": 632470,
    "hi-fi-rush": 1817230,
    "red-dead-redemption-2": 1174180,
}

STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")
_STEAM_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y")


def extract_steam_app_id(*values: str | None) -> int | None:
    for value in values:
        if not value:
            continue
        match = STEAM_APP_ID_RE.search(value)
        if match:
            return int(match.group(1))
    return None


def _parse_steam_release_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized or "coming soon" in normalized.lower() or "to be announced" in normalized.lower():
        return None
    for fmt in _STEAM_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _score_floor(review_label: str) -> float:
    return _REVIEW_LABEL_FLOORS.get(review_label.lower(), 0.0)


async def _lookup_steam_app_id(title: str, client: httpx.AsyncClient) -> int | None:
    try:
        response = await client.get(
            _STEAM_STORE_SEARCH_URL,
            params={"term": title, "l": "english", "cc": "US"},
            timeout=_TIMEOUT_SEARCH,
        )
        if response.is_success:
            items = response.json().get("items", [])
            if items:
                return int(items[0]["id"])
    except Exception:
        log.debug("Steam title search failed for %r", title)
    return None


async def get_steam_score(
    slug: str,
    title: str | None = None,
    steam_app_id: int | None = None,
) -> ExternalScore:
    app_id = steam_app_id or STEAM_APP_IDS.get(slug) or extract_steam_app_id(slug)

    async with httpx.AsyncClient(timeout=_TIMEOUT_REVIEWS) as client:
        if app_id is None and title:
            app_id = await _lookup_steam_app_id(title, client)

        if app_id is None:
            return ExternalScore(
                source="Steam", score=0, status="unavailable",
                detail="No Steam App ID found for this game.",
            )

        response = await client.get(
            _STEAM_APP_REVIEWS_URL.format(app_id=app_id),
            params={"json": 1, "filter": "summary", "language": "all", "purchase_type": "all"},
        )
        response.raise_for_status()

    summary = response.json().get("query_summary", {})
    total_reviews = int(summary.get("total_reviews") or 0)
    total_positive = int(summary.get("total_positive") or 0)
    review_label = str(summary.get("review_score_desc") or "Steam review score")

    if total_reviews == 0:
        return ExternalScore(
            source="Steam", score=0, status="unavailable",
            detail="Steam returned no review summary.",
        )

    raw_score = (total_positive / total_reviews) * 100
    score = round(max(raw_score, _score_floor(review_label)), 1)
    return ExternalScore(
        source="Steam",
        score=score,
        review_count=total_reviews,
        detail=f"{review_label}: {total_positive:,} / {total_reviews:,} positive ({score:.0f}%)",
        raw={
            "steam_app_id": app_id,
            "steam_review_summary": review_label,
        },
    )


async def get_steam_release_date(app_id: int) -> date | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT_DETAILS) as client:
        response = await client.get(
            _STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "filters": "release_date"},
        )
        if not response.is_success:
            return None

    payload = response.json().get(str(app_id), {})
    if not payload.get("success"):
        return None
    return _parse_steam_release_date(payload.get("data", {}).get("release_date", {}).get("date"))


async def get_steam_release_dates(app_ids: list[int]) -> dict[int, date]:
    if not app_ids:
        return {}

    async with httpx.AsyncClient(timeout=_TIMEOUT_BULK_DETAILS) as client:
        response = await client.get(
            _STEAM_APP_DETAILS_URL,
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
        parsed = _parse_steam_release_date(entry.get("data", {}).get("release_date", {}).get("date"))
        if parsed:
            result[app_id] = parsed
    return result
