import os

import httpx

from .types import ExternalScore


OC_DEFAULT_BASE = "https://api.opencritic.com/api"
OC_RAPIDAPI_BASE = "https://opencritic-api.p.rapidapi.com/api"


async def get_opencritic_score(title: str) -> ExternalScore:
    api_key = os.getenv("OPENCRITIC_API_KEY") or os.getenv("RAPIDAPI_KEY")
    if not api_key:
        return ExternalScore(
            source="OpenCritic",
            score=0,
            status="unavailable",
            detail="Set OPENCRITIC_API_KEY or RAPIDAPI_KEY to enable OpenCritic.",
        )

    api_base = (os.getenv("OPENCRITIC_API_BASE") or OC_RAPIDAPI_BASE).rstrip("/")

    headers: dict[str, str] = {"User-Agent": "GameMetrix/0.1"}
    # Support both RapidAPI format and a plain Bearer token.
    if "rapidapi" in api_base.lower():
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

    if (
        (percent_recommended is None or float(percent_recommended) < 0)
        and (top_critic_score is None or float(top_critic_score) < 0)
    ):
        return ExternalScore(
            source="OpenCritic",
            score=0,
            status="unavailable",
            detail="OpenCritic has no critic score for this game yet.",
        )

    detail_parts = []
    if percent_recommended is not None:
        detail_parts.append(f"{percent_recommended:.0f}% recommended")
    if top_critic_score is not None:
        detail_parts.append(f"Top Critic Avg {float(top_critic_score):.0f}")
    if tier:
        detail_parts.append(tier)
    if num_reviews:
        detail_parts.append(f"{num_reviews} critic reviews")

    return ExternalScore(
        source="OpenCritic",
        score=round(float(percent_recommended or top_critic_score), 1),
        review_count=num_reviews,
        detail=" — ".join(detail_parts) or None,
        raw={
            "opencritic_top_critic_score": round(float(top_critic_score or 0), 1),
            "opencritic_percent_recommended": round(float(percent_recommended or 0), 1),
        },
    )
