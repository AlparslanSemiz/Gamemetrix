import httpx

from .types import ExternalScore


STEAM_APP_IDS: dict[str, int] = {
    "baldurs-gate-3": 1086940,
    "elden-ring": 1245620,
    "hades": 1145360,
    "disco-elysium-the-final-cut": 632470,
    "hi-fi-rush": 1817230,
}


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


async def get_steam_score(slug: str, title: str | None = None) -> ExternalScore:
    app_id = STEAM_APP_IDS.get(slug)

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

    if total_reviews == 0:
        return ExternalScore(
            source="Steam",
            score=0,
            status="unavailable",
            detail="Steam returned no review summary.",
        )

    score = round((total_positive / total_reviews) * 100, 1)
    return ExternalScore(
        source="Steam",
        score=score,
        review_count=total_reviews,
        detail=f"{total_positive:,} / {total_reviews:,} positive ({score:.0f}%)",
    )
