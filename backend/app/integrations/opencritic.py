import httpx

from ..config import get_settings
from .types import ExternalScore


_OC_DEFAULT_BASE = "https://api.opencritic.com/api"
_OC_RAPIDAPI_BASE = "https://opencritic-api.p.rapidapi.com/api"
_RAPIDAPI_HOST = "opencritic-api.p.rapidapi.com"
_HTTP_TIMEOUT = 14


def _unavailable(detail: str) -> ExternalScore:
    return ExternalScore(source="OpenCritic", score=0, status="unavailable", detail=detail)


def _build_headers(api_key: str, api_base: str) -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": "GameMetrix/0.1"}
    # RapidAPI requires X-RapidAPI-Key; plain instances use Bearer auth.
    if "rapidapi" in api_base.lower():
        headers["X-RapidAPI-Key"] = api_key
        headers["X-RapidAPI-Host"] = _RAPIDAPI_HOST
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_score(game: dict) -> tuple[float | None, float | None]:
    top_critic = game.get("topCriticScore")
    percent = game.get("percentRecommended")
    return (
        float(top_critic) if top_critic is not None and float(top_critic) >= 0 else None,
        float(percent) if percent is not None and float(percent) >= 0 else None,
    )


def _build_detail(top_critic: float | None, percent: float | None, tier: str, num_reviews: int) -> str | None:
    parts: list[str] = []
    if percent is not None:
        parts.append(f"{percent:.0f}% recommended")
    if top_critic is not None:
        parts.append(f"Top Critic Avg {top_critic:.0f}")
    if tier:
        parts.append(tier)
    if num_reviews:
        parts.append(f"{num_reviews} critic reviews")
    return " — ".join(parts) or None


async def get_opencritic_score(title: str) -> ExternalScore:
    cfg = get_settings()
    # RAPIDAPI_KEY is required; fall back to OPENCRITIC_API_KEY if present.
    api_key = cfg.RAPIDAPI_KEY
    if not api_key:
        return _unavailable("Set RAPIDAPI_KEY to enable OpenCritic.")

    api_base = (cfg.OPENCRITIC_API_BASE or _OC_RAPIDAPI_BASE).rstrip("/")
    headers = _build_headers(api_key, api_base)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
        search_resp = await client.get(f"{api_base}/game/search", params={"criteria": title})
        if not search_resp.is_success:
            return _unavailable(f"OpenCritic search HTTP {search_resp.status_code}.")

        results = search_resp.json()
        if not results or not isinstance(results, list):
            return _unavailable("OpenCritic found no matching game.")

        game_id = results[0].get("id")
        if not game_id:
            return _unavailable("OpenCritic search result has no ID.")

        game_resp = await client.get(f"{api_base}/game/{game_id}")
        if not game_resp.is_success:
            return _unavailable(f"OpenCritic game fetch HTTP {game_resp.status_code}.")

    game = game_resp.json()
    top_critic, percent = _extract_score(game)
    if top_critic is None and percent is None:
        return _unavailable("OpenCritic has no critic score for this game yet.")

    num_reviews = int(game.get("numReviews") or 0)
    tier = str(game.get("tier") or "")
    final_score = percent if percent is not None else top_critic

    return ExternalScore(
        source="OpenCritic",
        score=round(float(final_score), 1),  # type: ignore[arg-type]
        review_count=num_reviews,
        detail=_build_detail(top_critic, percent, tier, num_reviews),
        raw={
            "opencritic_top_critic_score": round(top_critic or 0.0, 1),
            "opencritic_percent_recommended": round(percent or 0.0, 1),
        },
    )
