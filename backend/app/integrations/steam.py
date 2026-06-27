import re
from datetime import date, datetime

import httpx

from .types import ExternalScore


STEAM_APP_IDS: dict[str, int] = {
    "baldurs-gate-3": 1086940,
    "elden-ring": 1245620,
    "hades": 1145360,
    "disco-elysium-the-final-cut": 632470,
    "hi-fi-rush": 1817230,
    "red-dead-redemption-2": 1174180,
}


STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")
STEAM_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y")


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

    for fmt in STEAM_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    return None


def _score_floor(review_score_desc: str) -> float:
    normalized = review_score_desc.lower()
    if "overwhelmingly positive" in normalized:
        return 95.0
    if "very positive" in normalized:
        return 80.0
    if "mostly positive" in normalized:
        return 70.0
    if normalized == "positive":
        return 70.0
    return 0.0


async def _lookup_steam_app_id(title: str, client: httpx.AsyncClient) -> int | None:
    """Search Steam store by title and return the best-matching App ID."""
    try:
        response = await client.get(
            "https://store.steampowered.com/api/storesearch/",
            params={"term": title, "l": "english", "cc": "US"},
            timeout=8,
        )
        if not response.is_success:
            return None
        items = response.json().get("items", [])
        if items:
            return int(items[0]["id"])
    except Exception:
        pass
    return None


async def get_steam_score(
    slug: str,
    title: str | None = None,
    steam_app_id: int | None = None,
) -> ExternalScore:
    app_id = steam_app_id or STEAM_APP_IDS.get(slug) or extract_steam_app_id(slug)

    async with httpx.AsyncClient(timeout=12) as client:
        if app_id is None and title:
            app_id = await _lookup_steam_app_id(title, client)

        if app_id is None:
            return ExternalScore(
                source="Steam",
                score=0,
                status="unavailable",
                detail="No Steam App ID found for this game.",
            )

        url = f"https://store.steampowered.com/appreviews/{app_id}"
        params = {
            "json": 1,
            "filter": "summary",
            "language": "all",
            "purchase_type": "all",
        }

        response = await client.get(url, params=params)
        response.raise_for_status()

    summary = response.json().get("query_summary", {})
    total_reviews = int(summary.get("total_reviews") or 0)
    total_positive = int(summary.get("total_positive") or 0)
    review_score_desc = str(summary.get("review_score_desc") or "Steam review score")

    if total_reviews == 0:
        return ExternalScore(
            source="Steam",
            score=0,
            status="unavailable",
            detail="Steam returned no review summary.",
        )

    raw_score = (total_positive / total_reviews) * 100
    score = round(max(raw_score, _score_floor(review_score_desc)), 1)
    return ExternalScore(
        source="Steam",
        score=score,
        review_count=total_reviews,
        detail=(
            f"{review_score_desc}: {total_positive:,} / "
            f"{total_reviews:,} positive ({score:.0f}%)"
        ),
        raw={
            "steam_app_id": app_id,
            "steam_review_summary": review_score_desc,
        },
    )


async def get_steam_release_date(app_id: int) -> date | None:
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": app_id, "filters": "release_date"},
        )
        if not response.is_success:
            return None

    payload = response.json().get(str(app_id), {})
    if not payload.get("success"):
        return None

    release_date = payload.get("data", {}).get("release_date", {})
    return _parse_steam_release_date(release_date.get("date"))


async def get_steam_release_dates(app_ids: list[int]) -> dict[int, date]:
    if not app_ids:
        return {}

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://store.steampowered.com/api/appdetails",
            params={
                "appids": ",".join(str(app_id) for app_id in app_ids),
                "filters": "release_date",
            },
        )
        if not response.is_success:
            return {}

    payload = response.json()
    release_dates: dict[int, date] = {}
    for app_id in app_ids:
        app_payload = payload.get(str(app_id), {})
        if not app_payload.get("success"):
            continue
        release_date = app_payload.get("data", {}).get("release_date", {})
        parsed = _parse_steam_release_date(release_date.get("date"))
        if parsed:
            release_dates[app_id] = parsed

    return release_dates
