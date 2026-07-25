"""Steam review-summary score, with title-search app-id recovery."""

import logging

import httpx

from ..http_retry import DEFAULT_HEADERS, request_with_retry
from ..rate_limiter import get_rate_limiter
from ..steam_quota import stop_steam_requests_if_rate_limited
from ..title_matching import title_match_quality
from ..types import ExternalScore
from .client import (
    APP_REVIEWS_URL,
    STORE_SEARCH_URL,
    TIMEOUT_REVIEWS,
    TIMEOUT_SEARCH,
    extract_steam_app_id,
)

log = logging.getLogger(__name__)


def _unavailable(detail: str) -> ExternalScore:
    return ExternalScore(source="Steam", score=0, status="unavailable", detail=detail)


async def lookup_steam_app_id(title: str, client: httpx.AsyncClient) -> int | None:
    try:
        response = await client.get(
            STORE_SEARCH_URL,
            params={"term": title, "l": "english", "cc": "US"},
            timeout=TIMEOUT_SEARCH,
        )
        if stop_steam_requests_if_rate_limited(response) or not response.is_success:
            return None
        candidates = [
            item
            for item in response.json().get("items", [])
            if isinstance(item, dict) and item.get("id")
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda item: title_match_quality(title, str(item.get("name") or "")))
        if title_match_quality(title, str(best.get("name") or "")) > 0:
            return int(best["id"])
    except Exception:
        log.debug("Steam title search failed for %r", title)
    return None


async def get_steam_score(
    slug: str,
    title: str | None = None,
    steam_app_id: int | None = None,
) -> ExternalScore:
    app_id = steam_app_id or extract_steam_app_id(slug)
    lookup_used = False

    async with httpx.AsyncClient(timeout=TIMEOUT_REVIEWS, headers=DEFAULT_HEADERS) as client:
        if app_id is None and title:
            app_id = await lookup_steam_app_id(title, client)
            lookup_used = app_id is not None
        if app_id is None:
            return _unavailable("No Steam App ID found for this game.")

        if lookup_used and not await get_rate_limiter().acquire("Steam"):
            return _unavailable("Steam request budget was exhausted before the review lookup.")

        response = await request_with_retry(
            client,
            "GET",
            APP_REVIEWS_URL.format(app_id=app_id),
            params={"json": 1, "filter": "summary", "language": "all", "purchase_type": "all"},
        )
        if stop_steam_requests_if_rate_limited(response):
            return _unavailable("Steam rate limit reached.")
        response.raise_for_status()

    return _score_from_summary(app_id, response.json())


def _score_from_summary(app_id: int, payload: dict) -> ExternalScore:
    summary = payload.get("query_summary", {})
    try:
        total_reviews = int(summary.get("total_reviews") or 0)
        total_positive = int(summary.get("total_positive") or 0)
    except (TypeError, ValueError):
        total_reviews = total_positive = 0

    if total_reviews <= 0 or total_positive < 0 or total_positive > total_reviews:
        return _unavailable("Steam returned no review summary.")

    review_label = str(summary.get("review_score_desc") or "Steam review score")
    score = round((total_positive / total_reviews) * 100, 1)
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
