"""
OpenCritic service adapter.

Supports both the public opencritic.com API and the RapidAPI proxy.
When unavailable, the rest of the system continues normally.
"""

import logging
from datetime import date
from math import isfinite

import httpx

from ..config import OPENCRITIC_SEARCH_SOURCE, get_settings
from .http_retry import DEFAULT_HEADERS
from .opencritic import _best_search_result, _candidate_year, _extract_score
from .rate_limiter import get_rate_limiter
from .title_matching import titles_match
from .types import NormalizedGame, SourceHealth, bounded_int

log = logging.getLogger(__name__)

OC_RAPIDAPI_BASE = "https://opencritic-api.p.rapidapi.com"
OC_PUBLIC_BASE = "https://api.opencritic.com/api"


class OpenCriticService:
    def is_configured(self) -> bool:
        return get_settings().opencritic_configured()

    def _headers(self) -> dict[str, str]:
        cfg = get_settings()
        base = (cfg.OPENCRITIC_API_BASE or OC_RAPIDAPI_BASE).rstrip("/")
        headers: dict[str, str] = dict(DEFAULT_HEADERS)
        if "rapidapi" in base.lower():
            headers["X-RapidAPI-Key"] = cfg.RAPIDAPI_KEY
            headers["X-RapidAPI-Host"] = cfg.RAPIDAPI_HOST or "opencritic-api.p.rapidapi.com"
        else:
            api_key = cfg.OPENCRITIC_API_KEY or cfg.RAPIDAPI_KEY
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _base(self) -> str:
        cfg = get_settings()
        base = (cfg.OPENCRITIC_API_BASE or OC_RAPIDAPI_BASE).rstrip("/")
        # RapidAPI routes are rooted at /game and /meta. Older examples used
        # an extra /api segment, which now returns 404 for every request.
        if "rapidapi" in base.lower() and base.lower().endswith("/api"):
            return base[:-4]
        return base

    async def health_check(self) -> SourceHealth:
        if not self.is_configured():
            return SourceHealth(
                source="opencritic",
                configured=False,
                working=False,
                status="missing",
                message="OpenCritic credential not configured for the selected endpoint",
            )
        limiter = get_rate_limiter()
        if limiter.remaining("OpenCritic") <= 0:
            return SourceHealth(
                source="opencritic",
                configured=True,
                working=False,
                status="rate_limited",
                message="Configured OpenCritic request budget is exhausted",
            )
        return SourceHealth(
            source="opencritic",
            configured=True,
            working=True,
            status="ok",
            message="Configured; live OpenCritic search is manual to preserve the 24/day quota",
        )

    async def search_game(self, title: str, release_year: int | None = None) -> NormalizedGame | None:
        if not self.is_configured():
            return None
        limiter = get_rate_limiter()
        if (
            limiter.remaining("OpenCritic") < 2
            or limiter.remaining(OPENCRITIC_SEARCH_SOURCE) < 1
        ):
            return None
        # A search consumes both the plan-wide Requests object and the tighter
        # custom Searches object; the following detail consumes Requests again.
        if not await limiter.acquire("OpenCritic"):
            return None
        if not await limiter.acquire(OPENCRITIC_SEARCH_SOURCE):
            return None
        base = self._base()
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=14, headers=headers) as client:
                search = await client.get(f"{base}/game/search", params={"criteria": title})
                if not search.is_success:
                    log.warning("OC search HTTP %d for %r", search.status_code, title)
                    return None
                results = search.json()
                selected = _best_search_result(title, results, release_year)
                if selected is None:
                    return None
                game_id = selected.get("id")
                if not game_id:
                    return None
                if not await limiter.acquire("OpenCritic"):
                    return None
                detail = await client.get(f"{base}/game/{game_id}")
                if not detail.is_success:
                    return None
        except Exception as exc:
            log.warning("OC search failed for %r (%s)", title, type(exc).__name__)
            return None

        raw = detail.json()
        if not isinstance(raw, dict) or not titles_match(
            title,
            str(raw.get("name") or selected.get("name") or ""),
            expected_year=release_year,
            candidate_year=_candidate_year(raw) or _candidate_year(selected),
        ):
            return None
        return self._normalize(raw)

    def _normalize(self, raw: dict) -> NormalizedGame:
        release_date: date | None = None
        for key in ("firstReleaseDate", "releaseDate"):
            v = raw.get(key)
            if v:
                try:
                    release_date = date.fromisoformat(str(v)[:10])
                    break
                except ValueError:
                    pass

        score, pct_rec = _extract_score(raw)

        platforms = [
            str(platform["name"])[:100]
            for platform in (raw.get("platforms") or [])
            if isinstance(platform, dict) and platform.get("name")
        ]

        score_count = bounded_int(raw.get("numReviews"))

        return NormalizedGame(
            source="OpenCritic",
            external_id=str(raw.get("id", "")),
            name=str(raw.get("name") or "")[:500],
            external_url=f"https://opencritic.com/game/{raw.get('id')}/{raw.get('url', '')}",
            release_date=release_date,
            platforms=platforms,
            genres=[],
            score=round(score, 1) if score is not None and isfinite(score) else None,
            score_count=score_count,
            is_critic_score=True,
            raw={
                "opencritic_id": raw.get("id"),
                "top_critic_score": score,
                "percent_recommended": pct_rec,
                "tier": raw.get("tier"),
                "num_reviews": raw.get("numReviews"),
            },
        )


opencritic_service = OpenCriticService()
