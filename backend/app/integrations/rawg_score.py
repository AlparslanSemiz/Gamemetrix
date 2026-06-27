import os
from datetime import date

import httpx

from .types import ExternalScore


RAWG_GAMES_URL = "https://api.rawg.io/api/games"


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

    api_key = os.getenv("RAWG_API_KEY")
    if not api_key:
        return ExternalScore(
            source="Metacritic",
            score=0,
            status="unavailable",
            detail="Set RAWG_API_KEY to enable Metacritic via RAWG.",
        )

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(
            RAWG_GAMES_URL,
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
            source="Metacritic",
            score=0,
            status="unavailable",
            detail="RAWG returned no matching game.",
        )

    raw_game = results[0]
    metacritic = raw_game.get("metacritic")
    if metacritic is None:
        return ExternalScore(
            source="Metacritic",
            score=0,
            status="unavailable",
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
    api_key = os.getenv("RAWG_API_KEY")
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(
            RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 1},
        )
        if not response.is_success:
            return None

    results = response.json().get("results", [])
    if not results:
        return None

    return _parse_rawg_date(results[0].get("released"))


async def get_rawg_game_metadata(title: str) -> dict | None:
    api_key = os.getenv("RAWG_API_KEY")
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=14) as client:
        search_response = await client.get(
            RAWG_GAMES_URL,
            params={"key": api_key, "search": title, "page_size": 1},
        )
        if not search_response.is_success:
            return None

        results = search_response.json().get("results", [])
        if not results:
            return None

        raw_game = results[0]
        rawg_id = raw_game.get("id")
        if not rawg_id:
            return raw_game

        detail_response = await client.get(
            f"{RAWG_GAMES_URL}/{rawg_id}",
            params={"key": api_key},
        )
        if detail_response.is_success:
            detail = detail_response.json()
            detail.setdefault("background_image", raw_game.get("background_image"))
            detail.setdefault("released", raw_game.get("released"))
            detail.setdefault("metacritic", raw_game.get("metacritic"))
            detail.setdefault("genres", raw_game.get("genres", []))
            detail.setdefault("platforms", raw_game.get("platforms", []))
            return detail

    return raw_game
