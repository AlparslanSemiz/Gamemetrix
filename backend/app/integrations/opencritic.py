import os

import httpx

from .types import ExternalScore


OC_DEFAULT_BASE = "https://api.opencritic.com/api"


async def get_opencritic_score(title: str) -> ExternalScore:
    api_base = (os.getenv("OPENCRITIC_API_BASE") or OC_DEFAULT_BASE).rstrip("/")
    api_key = os.getenv("OPENCRITIC_API_KEY")

    headers: dict[str, str] = {"User-Agent": "GameMetrix/0.1"}
    if api_key:
        # Support both RapidAPI format and a plain Bearer token.
        if "rapidapi" in api_base.lower() or "rapidapi" in (api_key or ""):
            headers["X-RapidAPI-Key"] = api_key
            headers["X-RapidAPI-Host"] = "opencritic-api.p.rapidapi.com"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=14, headers=headers) as client:
        search_response = await client.get(
            f"{api_base}/game/search",
            params={"criteria": title},
        )
        if not search_response.is_success:
            return ExternalScore(
                source="OpenCritic",
                score=0,
                status="unavailable",
                detail=f"OpenCritic search HTTP {search_response.status_code}.",
            )

        results = search_response.json()
        if not results or not isinstance(results, list):
            return ExternalScore(
                source="OpenCritic",
                score=0,
                status="unavailable",
                detail="OpenCritic found no matching game.",
            )

        game_id = results[0].get("id")
        if not game_id:
            return ExternalScore(
                source="OpenCritic",
                score=0,
                status="unavailable",
                detail="OpenCritic search result has no ID.",
            )

        game_response = await client.get(f"{api_base}/game/{game_id}")
        if not game_response.is_success:
            return ExternalScore(
                source="OpenCritic",
                score=0,
                status="unavailable",
                detail=f"OpenCritic game fetch HTTP {game_response.status_code}.",
            )

    game = game_response.json()
    top_critic_score = game.get("topCriticScore")
    num_reviews = int(game.get("numReviews") or 0)
    tier = str(game.get("tier") or "")
    percent_recommended = game.get("percentRecommended")

    if top_critic_score is None or float(top_critic_score) < 0:
        return ExternalScore(
            source="OpenCritic",
            score=0,
            status="unavailable",
            detail="OpenCritic has no critic score for this game yet.",
        )

    detail_parts = []
    if tier:
        detail_parts.append(tier)
    if num_reviews:
        detail_parts.append(f"{num_reviews} critic reviews")
    if percent_recommended is not None:
        detail_parts.append(f"{percent_recommended:.0f}% recommended")

    return ExternalScore(
        source="OpenCritic",
        score=round(float(top_critic_score), 1),
        review_count=num_reviews,
        detail=" — ".join(detail_parts) or None,
    )
