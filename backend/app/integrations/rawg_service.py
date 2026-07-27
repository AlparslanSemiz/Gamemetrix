"""
RAWG service adapter.

RAWG is used for enrichment (screenshots, tags, playtime, store links,
description, platform metadata) rather than as a rating source.
"""

import logging
import time
from datetime import date

import httpx

from ..config import get_settings
from .rate_limiter import get_rate_limiter
from .rawg_quota import stop_rawg_requests_if_quota_exhausted
from .title_matching import title_match_quality
from .types import NormalizedGame, SourceHealth, bounded_float, bounded_int

log = logging.getLogger(__name__)

RAWG_BASE = "https://api.rawg.io/api"
SMOKE_TEST_TITLE = "Portal 2"


class RAWGService:
    def is_configured(self) -> bool:
        return get_settings().rawg_configured()

    async def health_check(self) -> SourceHealth:
        if not self.is_configured():
            return SourceHealth(
                source="rawg",
                configured=False,
                working=False,
                status="missing",
                message="RAWG_API_KEY not configured",
            )
        cfg = get_settings()
        if not await get_rate_limiter().acquire("RAWG"):
            return SourceHealth(
                source="rawg",
                configured=True,
                working=False,
                status="rate_limited",
                message="Configured RAWG request budget is exhausted",
            )
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(
                    f"{RAWG_BASE}/games",
                    params={"key": cfg.RAWG_API_KEY, "search": SMOKE_TEST_TITLE, "page_size": 1},
                )
            latency = int((time.monotonic() - t0) * 1000)
            if stop_rawg_requests_if_quota_exhausted(response):
                return SourceHealth(
                    source="rawg",
                    configured=True,
                    working=False,
                    status="rate_limited",
                    message=f"RAWG quota or rate limit reached (HTTP {response.status_code})",
                    latency_ms=latency,
                )
            if response.status_code in {401, 403}:
                return SourceHealth(
                    source="rawg",
                    configured=True,
                    working=False,
                    status="invalid_key",
                    message=f"RAWG API key rejected (HTTP {response.status_code})",
                    latency_ms=latency,
                )
            if response.status_code == 429:
                return SourceHealth(
                    source="rawg", configured=True, working=False,
                    status="rate_limited", message="RAWG quota or rate limit reached (HTTP 429)",
                    latency_ms=latency,
                )
            if not response.is_success:
                return SourceHealth(
                    source="rawg",
                    configured=True,
                    working=False,
                    status="provider_error" if response.status_code >= 500 else "failing",
                    message=f"RAWG endpoint returned HTTP {response.status_code}",
                    latency_ms=latency,
                )
            results = response.json().get("results", [])
            if results:
                return SourceHealth(
                    source="rawg",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f'Test query "{SMOKE_TEST_TITLE}" returned result',
                    latency_ms=latency,
                )
            return SourceHealth(
                source="rawg",
                configured=True,
                working=False,
                status="failing",
                message="RAWG returned no results for test query",
                latency_ms=latency,
            )
        except httpx.TimeoutException:
            return SourceHealth(
                source="rawg", configured=True, working=False,
                status="timeout", message="RAWG health check timed out",
            )
        except Exception as exc:
            return SourceHealth(
                source="rawg",
                configured=True,
                working=False,
                status="failing",
                message=f"RAWG request failed: {type(exc).__name__}",
            )

    async def search_game(
        self,
        title: str,
        page_size: int = 10,
        release_year: int | None = None,
    ) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        if not await get_rate_limiter().acquire("RAWG"):
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{RAWG_BASE}/games",
                    params={"key": cfg.RAWG_API_KEY, "search": title, "page_size": max(1, min(page_size, 10))},
                )
                if stop_rawg_requests_if_quota_exhausted(resp):
                    return None
                resp.raise_for_status()
        except Exception as exc:
            # HTTPX exception strings include the request URL; RAWG puts its
            # secret in the query string, so never log the exception value.
            log.warning("RAWG search failed for %r (%s)", title, type(exc).__name__)
            return None

        results = resp.json().get("results", [])
        candidates = [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []
        if not candidates:
            return None

        def quality(row: dict) -> float:
            try:
                candidate_year = date.fromisoformat(str(row.get("released") or "")).year
            except ValueError:
                candidate_year = None
            return title_match_quality(
                title,
                str(row.get("name") or ""),
                expected_year=release_year,
                candidate_year=candidate_year,
            )

        best = max(candidates, key=quality)
        return self._normalize(best) if quality(best) > 0 else None

    async def get_by_rawg_id(self, rawg_id: int) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        if not await get_rate_limiter().acquire("RAWG"):
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{RAWG_BASE}/games/{rawg_id}",
                    params={"key": cfg.RAWG_API_KEY},
                )
                if stop_rawg_requests_if_quota_exhausted(resp):
                    return None
                resp.raise_for_status()
        except Exception as exc:
            log.warning("RAWG get by id %d failed (%s)", rawg_id, type(exc).__name__)
            return None

        return self._normalize(resp.json())

    def _normalize(self, raw: dict) -> NormalizedGame:
        platforms = [
            str(p["platform"]["name"])[:100]
            for p in raw.get("platforms") or []
            if isinstance(p, dict)
            and isinstance(p.get("platform"), dict)
            and p["platform"].get("name")
        ]
        genres = [
            str(genre["name"])[:100]
            for genre in raw.get("genres") or []
            if isinstance(genre, dict) and genre.get("name")
        ]

        release_date: date | None = None
        released = raw.get("released")
        if released:
            try:
                release_date = date.fromisoformat(str(released))
            except (TypeError, ValueError):
                pass

        developer: str | None = None
        publisher: str | None = None
        for dev in raw.get("developers") or []:
            if isinstance(dev, dict) and dev.get("name"):
                developer = str(dev["name"])[:200]
                break
        for pub in raw.get("publishers") or []:
            if isinstance(pub, dict) and pub.get("name"):
                publisher = str(pub["name"])[:200]
                break

        metacritic = bounded_float(raw.get("metacritic"), maximum=100.0)
        score = metacritic
        # RAWG rating is 0–5 scale; normalize to 0–100
        rawg_rating = bounded_float(raw.get("rating"), maximum=5.0)
        rawg_score = round(rawg_rating * 20, 1) if rawg_rating is not None else None

        return NormalizedGame(
            source="RAWG",
            external_id=str(raw.get("id", "")),
            name=str(raw.get("name") or "")[:500],
            external_slug=str(raw["slug"])[:200] if raw.get("slug") else None,
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            developer=developer,
            publisher=publisher,
            summary=str(raw["description_raw"])[:20_000] if raw.get("description_raw") else None,
            cover_url=str(raw["background_image"])[:500] if raw.get("background_image") else None,
            score=score if score is not None else rawg_score,
            score_count=bounded_int(raw.get("ratings_count")),
            is_critic_score=metacritic is not None,
            raw={
                "rawg_id": raw.get("id"),
                "metacritic": metacritic,
                "rawg_rating": rawg_rating,
                "rawg_score_normalized": rawg_score,
                "playtime": raw.get("playtime"),
                "website": raw.get("website"),
                "tags": [t.get("name") for t in (raw.get("tags") or []) if isinstance(t, dict)],
                "stores": [
                    s["store"]["name"]
                    for s in (raw.get("stores") or [])
                    if isinstance(s, dict) and isinstance(s.get("store"), dict)
                ],
                "short_screenshots": [
                    s.get("image") for s in (raw.get("short_screenshots") or []) if isinstance(s, dict)
                ],
            },
        )


rawg_service = RAWGService()
