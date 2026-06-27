"""
OpenCritic service adapter.

Supports both the public opencritic.com API and the RapidAPI proxy.
When unavailable, the rest of the system continues normally.
"""

import logging
import time
from datetime import date

import httpx

from ..config import get_settings
from .types import NormalizedGame, SourceHealth

log = logging.getLogger(__name__)

OC_RAPIDAPI_BASE = "https://opencritic-api.p.rapidapi.com/api"
OC_PUBLIC_BASE = "https://api.opencritic.com/api"
SMOKE_TEST_TITLE = "Portal 2"


class OpenCriticService:
    def is_configured(self) -> bool:
        return get_settings().opencritic_configured()

    def _headers(self) -> dict[str, str]:
        cfg = get_settings()
        base = (cfg.OPENCRITIC_API_BASE or OC_RAPIDAPI_BASE).rstrip("/")
        headers: dict[str, str] = {"User-Agent": "GameMetrix/0.1"}
        if "rapidapi" in base.lower():
            headers["X-RapidAPI-Key"] = cfg.RAPIDAPI_KEY
            headers["X-RapidAPI-Host"] = cfg.RAPIDAPI_HOST or "opencritic-api.p.rapidapi.com"
        elif cfg.RAPIDAPI_KEY:
            headers["Authorization"] = f"Bearer {cfg.RAPIDAPI_KEY}"
        return headers

    def _base(self) -> str:
        cfg = get_settings()
        return (cfg.OPENCRITIC_API_BASE or OC_RAPIDAPI_BASE).rstrip("/")

    async def health_check(self) -> SourceHealth:
        if not self.is_configured():
            return SourceHealth(
                source="opencritic",
                configured=False,
                working=False,
                status="missing",
                message="RAPIDAPI_KEY not configured",
            )
        try:
            t0 = time.monotonic()
            game = await self.search_game(SMOKE_TEST_TITLE)
            latency = int((time.monotonic() - t0) * 1000)
            if game:
                return SourceHealth(
                    source="opencritic",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f'Test query "{SMOKE_TEST_TITLE}" returned result',
                    latency_ms=latency,
                )
            return SourceHealth(
                source="opencritic",
                configured=True,
                working=False,
                status="failing",
                message="OpenCritic returned no results for test query",
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="opencritic",
                configured=True,
                working=False,
                status="failing",
                message=f"OpenCritic request failed: {type(exc).__name__}",
            )

    async def search_game(self, title: str) -> NormalizedGame | None:
        if not self.is_configured():
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
                if not results or not isinstance(results, list):
                    return None
                game_id = results[0].get("id")
                if not game_id:
                    return None
                detail = await client.get(f"{base}/game/{game_id}")
                if not detail.is_success:
                    return None
        except Exception as exc:
            log.warning("OC search failed for %r: %s", title, exc)
            return None

        return self._normalize(detail.json())

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

        top_critic = raw.get("topCriticScore")
        pct_rec = raw.get("percentRecommended")
        score = top_critic if top_critic is not None and float(top_critic) >= 0 else None
        if score is None and pct_rec is not None and float(pct_rec) >= 0:
            score = float(pct_rec)

        platforms = [p.get("name", "") for p in (raw.get("platforms") or []) if isinstance(p, dict)]

        return NormalizedGame(
            source="OpenCritic",
            external_id=str(raw.get("id", "")),
            name=raw.get("name", ""),
            external_url=f"https://opencritic.com/game/{raw.get('id')}/{raw.get('url', '')}",
            release_date=release_date,
            platforms=platforms,
            genres=[],
            score=round(float(score), 1) if score is not None else None,
            score_count=int(raw.get("numReviews") or 0) or None,
            is_critic_score=True,
            raw={
                "opencritic_id": raw.get("id"),
                "top_critic_score": top_critic,
                "percent_recommended": pct_rec,
                "tier": raw.get("tier"),
                "num_reviews": raw.get("numReviews"),
            },
        )


opencritic_service = OpenCriticService()
