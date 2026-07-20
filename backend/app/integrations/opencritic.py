import httpx
from math import isfinite

from ..config import OPENCRITIC_SEARCH_SOURCE, get_settings
from .http_retry import DEFAULT_HEADERS
from .rate_limiter import get_rate_limiter
from .title_matching import title_match_quality, titles_match
from .types import ExternalScore


_OC_DEFAULT_BASE = "https://api.opencritic.com/api"
_OC_RAPIDAPI_BASE = "https://opencritic-api.p.rapidapi.com"
_RAPIDAPI_HOST = "opencritic-api.p.rapidapi.com"
_HTTP_TIMEOUT = 14


def _unavailable(detail: str) -> ExternalScore:
    return ExternalScore(source="OpenCritic", score=0, status="unavailable", detail=detail)


def _build_headers(api_key: str, api_base: str) -> dict[str, str]:
    headers: dict[str, str] = dict(DEFAULT_HEADERS)
    # RapidAPI requires X-RapidAPI-Key; plain instances use Bearer auth.
    if "rapidapi" in api_base.lower():
        headers["X-RapidAPI-Key"] = api_key
        headers["X-RapidAPI-Host"] = _RAPIDAPI_HOST
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_score(game: dict) -> tuple[float | None, float | None]:
    def bounded(value: object) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) and 0 <= number <= 100 else None

    return bounded(game.get("topCriticScore")), bounded(game.get("percentRecommended"))


def _candidate_year(raw: dict) -> int | None:
    for key in ("firstReleaseDate", "releaseDate"):
        value = str(raw.get(key) or "")
        if value[:4].isdigit():
            return int(value[:4])
    return None


def _best_search_result(title: str, results: object, release_year: int | None) -> dict | None:
    if not isinstance(results, list):
        return None
    candidates = [row for row in results if isinstance(row, dict) and row.get("id")]
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda row: title_match_quality(
            title,
            str(row.get("name") or ""),
            expected_year=release_year,
            candidate_year=_candidate_year(row),
        ),
    )
    return best if title_match_quality(
        title,
        str(best.get("name") or ""),
        expected_year=release_year,
        candidate_year=_candidate_year(best),
    ) > 0 else None


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


async def get_opencritic_score(
    title: str,
    release_year: int | None = None,
    opencritic_id: str | int | None = None,
) -> ExternalScore:
    cfg = get_settings()
    api_base = (cfg.OPENCRITIC_API_BASE or _OC_RAPIDAPI_BASE).rstrip("/")
    is_rapidapi = "rapidapi" in api_base.lower()
    api_key = cfg.RAPIDAPI_KEY if is_rapidapi else (cfg.OPENCRITIC_API_KEY or cfg.RAPIDAPI_KEY)
    if not api_key:
        return _unavailable("Set the OpenCritic credential for the configured endpoint.")

    if "rapidapi" in api_base.lower() and api_base.lower().endswith("/api"):
        api_base = api_base[:-4]
    headers = _build_headers(api_key, api_base)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
        selected: dict = {}
        results: object = []
        game_id = opencritic_id
        if game_id is None:
            # The search endpoint has its own, much tighter provider ceiling, so it
            # draws from a separate bucket than the detail lookup below.
            if not await get_rate_limiter().acquire(OPENCRITIC_SEARCH_SOURCE):
                return _unavailable("OpenCritic search budget exhausted — will retry next cycle.")
            search_resp = await client.get(f"{api_base}/game/search", params={"criteria": title})
            if search_resp.status_code == 429:
                return _unavailable("OpenCritic rate limit hit (RapidAPI quota exceeded).")
            if not search_resp.is_success:
                return _unavailable(f"OpenCritic search HTTP {search_resp.status_code}.")

            results = search_resp.json()
            matched = _best_search_result(title, results, release_year)
            if matched is None:
                return _unavailable("OpenCritic found no matching game.")
            selected = matched
            game_id = selected.get("id")
            if not game_id:
                return _unavailable("OpenCritic search result has no ID.")

        # One general-bucket slot was already acquired by the caller for this
        # detail request; the search above drew from its own bucket.
        game_resp = await client.get(f"{api_base}/game/{game_id}")
        if game_resp.status_code == 429:
            return _unavailable("OpenCritic rate limit hit (RapidAPI quota exceeded).")
        if not game_resp.is_success:
            return _unavailable(f"OpenCritic game fetch HTTP {game_resp.status_code}.")

    game = game_resp.json()
    if not isinstance(game, dict) or not titles_match(
        title,
        str(game.get("name") or selected.get("name") or ""),
        expected_year=release_year,
        candidate_year=_candidate_year(game) or _candidate_year(selected),
    ):
        return _unavailable("OpenCritic detail did not match the requested game.")
    top_critic, percent = _extract_score(game)
    if top_critic is None:
        return _unavailable("OpenCritic has no Top Critic Score for this game yet.")

    try:
        num_reviews = max(0, int(game.get("numReviews") or 0))
    except (TypeError, ValueError):
        num_reviews = 0
    tier = str(game.get("tier") or "")

    return ExternalScore(
        source="OpenCritic",
        score=round(top_critic, 1),
        review_count=num_reviews,
        detail=_build_detail(top_critic, percent, tier, num_reviews),
        raw={
            "opencritic_id": game_id,
            "opencritic_top_critic_score": round(top_critic or 0.0, 1),
            "opencritic_percent_recommended": round(percent or 0.0, 1),
            "search_response": results,
            "response": game,
        },
    )
