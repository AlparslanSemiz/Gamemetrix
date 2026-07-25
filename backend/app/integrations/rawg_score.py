from datetime import date
from math import isfinite

import httpx

from ..config import get_settings
from .rate_limiter import get_rate_limiter
from .rawg_quota import stop_rawg_requests_if_quota_exhausted
from .title_matching import title_match_quality
from .types import ExternalScore


_RAWG_GAMES_URL = "https://api.rawg.io/api/games"
_HTTP_TIMEOUT_SEARCH = 12
_HTTP_TIMEOUT_DETAIL = 14


def _parse_rawg_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _best_rawg_result(title: str, results: object, release_year: int | None = None) -> dict | None:
    if not isinstance(results, list):
        return None
    candidates = [row for row in results if isinstance(row, dict)]
    if not candidates:
        return None

    def quality(row: dict) -> float:
        released = _parse_rawg_date(str(row.get("released") or ""))
        return title_match_quality(
            title,
            str(row.get("name") or ""),
            expected_year=release_year,
            candidate_year=released.year if released else None,
        )

    best = max(candidates, key=quality)
    return best if quality(best) > 0 else None


def _bounded_number(value: object, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and minimum <= number <= maximum else None


async def get_rawg_metacritic_score(
    title: str,
    cached_value: int | None = None,
    release_year: int | None = None,
) -> ExternalScore:
    if cached_value is not None:
        return ExternalScore(
            source="Metacritic",
            score=float(cached_value),
            detail="Metacritic score cached from RAWG.",
        )

    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return ExternalScore(
            source="Metacritic",
            score=0,
            status="unavailable",
            detail="Set RAWG_API_KEY to enable Metacritic via RAWG.",
        )

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEARCH) as client:
        response = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 10},
        )
        stop_rawg_requests_if_quota_exhausted(response)
        if not response.is_success:
            return ExternalScore(
                source="Metacritic",
                score=0,
                status="unavailable",
                detail=f"RAWG search HTTP {response.status_code}.",
            )

    raw_game = _best_rawg_result(title, response.json().get("results", []), release_year)
    if raw_game is None:
        return ExternalScore(
            source="Metacritic", score=0, status="unavailable",
            detail="RAWG returned no matching game.",
        )

    metacritic = _bounded_number(raw_game.get("metacritic"), 0, 100)
    if metacritic is None:
        return ExternalScore(
            source="Metacritic", score=0, status="unavailable",
            detail="RAWG result has no Metacritic score.",
        )

    return ExternalScore(
        source="Metacritic",
        score=metacritic,
        detail="Metacritic score via RAWG.",
        review_count=int(raw_game.get("ratings_count") or raw_game.get("reviews_count") or 0),
        raw={
            "rawg_id": int(raw_game.get("id") or 0),
            "rawg_name": str(raw_game.get("name") or title),
            "rawg_slug": raw_game.get("slug"),
            "rawg_url": f"https://rawg.io/games/{raw_game.get('slug')}" if raw_game.get("slug") else None,
            "response": raw_game,
        },
    )


async def get_rawg_rating_score(title: str, release_year: int | None = None) -> ExternalScore:
    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return ExternalScore(
            source="RAWG",
            score=0,
            status="unavailable",
            detail="Set RAWG_API_KEY to enable RAWG rating fallback.",
        )

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEARCH) as client:
        response = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 10},
        )
        stop_rawg_requests_if_quota_exhausted(response)
        if not response.is_success:
            return ExternalScore(
                source="RAWG",
                score=0,
                status="unavailable",
                detail=f"RAWG search HTTP {response.status_code}.",
            )

    raw_game = _best_rawg_result(title, response.json().get("results", []), release_year)
    if raw_game is None:
        return ExternalScore(
            source="RAWG",
            score=0,
            status="unavailable",
            detail="RAWG returned no matching game.",
        )

    raw_rating = _bounded_number(raw_game.get("rating"), 0, 5)
    if raw_rating is None:
        return ExternalScore(
            source="RAWG",
            score=0,
            status="unavailable",
            detail="RAWG result has no community rating.",
            raw={"response": raw_game},
        )

    score = round(raw_rating * 20, 1)
    review_count = int(raw_game.get("ratings_count") or raw_game.get("reviews_count") or 0)
    return ExternalScore(
        source="RAWG",
        score=score,
        review_count=review_count,
        detail=f"RAWG community rating {raw_rating:.2f}/5 ({review_count} ratings)",
        raw={
            "rawg_id": int(raw_game.get("id") or 0),
            "rawg_name": str(raw_game.get("name") or title),
            "rawg_slug": raw_game.get("slug"),
            "rawg_url": f"https://rawg.io/games/{raw_game.get('slug')}" if raw_game.get("slug") else None,
            "response": raw_game,
        },
    )


async def get_rawg_release_date(title: str) -> date | None:
    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEARCH) as client:
        response = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 10},
        )
        stop_rawg_requests_if_quota_exhausted(response)
        if not response.is_success:
            return None

    result = _best_rawg_result(title, response.json().get("results", []))
    return _parse_rawg_date(result.get("released")) if result else None


async def get_rawg_game_metadata(title: str) -> dict | None:
    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_DETAIL) as client:
        search_resp = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 10},
        )
        stop_rawg_requests_if_quota_exhausted(search_resp)
        if not search_resp.is_success:
            return None

        raw_game = _best_rawg_result(title, search_resp.json().get("results", []))
        if raw_game is None:
            return None
        rawg_id = raw_game.get("id")
        if not rawg_id:
            return raw_game

        if not await get_rate_limiter().acquire("RAWG"):
            return raw_game
        detail_resp = await client.get(
            f"{_RAWG_GAMES_URL}/{rawg_id}",
            params={"key": api_key},
        )
        stop_rawg_requests_if_quota_exhausted(detail_resp)
        if not detail_resp.is_success:
            return raw_game

    detail = detail_resp.json()
    # Merge search-level fields that the detail endpoint may omit.
    for field in ("background_image", "released", "metacritic", "genres", "platforms"):
        detail.setdefault(field, raw_game.get(field, [] if field in ("genres", "platforms") else None))
    return detail
