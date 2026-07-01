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
    "resident-evil-4-remake": 2050650,
    "resident-evil-4": 254700,
    "resident-evil-2-remake": 883710,
    "resident-evil-village": 1196590,
    "sekiro-shadows-die-twice": 814380,
    "dark-souls-3": 374320,
    "cyberpunk-2077": 1091500,
    "god-of-war-2018": 1593500,
    "god-of-war-ragnarok": 2322010,
}

STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")
_STEAM_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y")


def extract_steam_app_id(*values: str | None) -> int | None:
    for value in values:
        if not value:
            continue
        if value in STEAM_APP_IDS:
            return STEAM_APP_IDS[value]
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

    payload = response.json()
    summary = payload.get("query_summary", {})
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
            "query_summary": summary,
            "response": payload,
        },
    )


_MAX_SCREENSHOTS = 16


async def fetch_steam_screenshots(app_id: int) -> list[str]:
    """Return up to _MAX_SCREENSHOTS full-resolution screenshot URLs for a Steam app."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_DETAILS) as client:
        response = await client.get(
            _STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "filters": "screenshots", "cc": "us"},
        )
        if not response.is_success:
            return []

    payload = response.json().get(str(app_id), {})
    if not payload.get("success"):
        return []

    return [
        s["path_full"]
        for s in (payload.get("data", {}).get("screenshots") or [])
        if isinstance(s, dict) and s.get("path_full")
    ][:_MAX_SCREENSHOTS]


async def fetch_steam_dlcs(app_id: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=_TIMEOUT_DETAILS) as client:
        response = await client.get(
            _STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "cc": "us"},
        )
        if not response.is_success:
            return []

        payload = response.json().get(str(app_id), {})
        if not payload.get("success"):
            return []

        dlc_ids = [
            int(item)
            for item in (payload.get("data", {}).get("dlc") or [])
            if str(item).isdigit()
        ]
        if not dlc_ids:
            return []

        dlcs: list[dict] = []
        for dlc_id in dlc_ids[:24]:
            detail_response = await client.get(
                _STEAM_APP_DETAILS_URL,
                params={"appids": dlc_id, "filters": "basic"},
                timeout=_TIMEOUT_DETAILS,
            )
            if not detail_response.is_success:
                continue
            entry = detail_response.json().get(str(dlc_id), {})
            data = entry.get("data", {}) if entry.get("success") else {}
            title = data.get("name")
            if not title:
                continue
            release = _parse_steam_release_date((data.get("release_date") or {}).get("date"))
            dlcs.append({
                "id": dlc_id,
                "title": title,
                "slug": str(dlc_id),
                "release_date": release.isoformat() if release else None,
                "release_year": release.year if release else None,
                "cover_url": data.get("header_image") or "",
                "url": f"https://store.steampowered.com/app/{dlc_id}/",
                "type": data.get("type") or "dlc",
            })
        return dlcs


async def get_steam_release_date(app_id: int) -> date | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT_DETAILS) as client:
        response = await client.get(
            _STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "filters": "release_date", "cc": "us"},
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
