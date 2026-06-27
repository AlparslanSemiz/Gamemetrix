from datetime import date

import httpx

from ..config import get_settings
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


async def get_rawg_metacritic_score(
    title: str,
    cached_value: int | None = None,
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
            params={"key": api_key, "search": title, "page_size": 1},
        )
        if not response.is_success:
            return ExternalScore(
                source="Metacritic",
                score=0,
                status="unavailable",
                detail=f"RAWG search HTTP {response.status_code}.",
            )

    results = response.json().get("results", [])
    if not results:
        return ExternalScore(
            source="Metacritic", score=0, status="unavailable",
            detail="RAWG returned no matching game.",
        )

    raw_game = results[0]
    metacritic = raw_game.get("metacritic")
    if metacritic is None:
        return ExternalScore(
            source="Metacritic", score=0, status="unavailable",
            detail="RAWG result has no Metacritic score.",
        )

    return ExternalScore(
        source="Metacritic",
        score=float(metacritic),
        detail="Metacritic score via RAWG.",
        raw={
            "rawg_id": int(raw_game.get("id") or 0),
            "rawg_name": str(raw_game.get("name") or title),
        },
    )


async def get_rawg_release_date(title: str) -> date | None:
    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEARCH) as client:
        response = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 1},
        )
        if not response.is_success:
            return None

    results = response.json().get("results", [])
    return _parse_rawg_date(results[0].get("released")) if results else None


async def get_rawg_game_metadata(title: str) -> dict | None:
    api_key = get_settings().RAWG_API_KEY
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_DETAIL) as client:
        search_resp = await client.get(
            _RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 1},
        )
        if not search_resp.is_success:
            return None

        results = search_resp.json().get("results", [])
        if not results:
            return None

        raw_game = results[0]
        rawg_id = raw_game.get("id")
        if not rawg_id:
            return raw_game

        detail_resp = await client.get(
            f"{_RAWG_GAMES_URL}/{rawg_id}",
            params={"key": api_key},
        )
        if not detail_resp.is_success:
            return raw_game

    detail = detail_resp.json()
    # Merge search-level fields that the detail endpoint may omit.
    for field in ("background_image", "released", "metacritic", "genres", "platforms"):
        detail.setdefault(field, raw_game.get(field, [] if field in ("genres", "platforms") else None))
    return detail
