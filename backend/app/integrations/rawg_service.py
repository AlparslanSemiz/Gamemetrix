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
from .types import NormalizedGame, SourceHealth

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
        try:
            t0 = time.monotonic()
            game = await self.search_game(SMOKE_TEST_TITLE)
            latency = int((time.monotonic() - t0) * 1000)
            if game:
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
        except Exception as exc:
            return SourceHealth(
                source="rawg",
                configured=True,
                working=False,
                status="failing",
                message=f"RAWG request failed: {type(exc).__name__}",
            )

    async def search_game(self, title: str, page_size: int = 3) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{RAWG_BASE}/games",
                    params={"key": cfg.RAWG_API_KEY, "search": title, "page_size": page_size},
                )
                resp.raise_for_status()
        except Exception as exc:
            log.warning("RAWG search failed for %r: %s", title, exc)
            return None

        results = resp.json().get("results", [])
        if not results:
            return None
        return self._normalize(results[0])

    async def get_by_rawg_id(self, rawg_id: int) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    f"{RAWG_BASE}/games/{rawg_id}",
                    params={"key": cfg.RAWG_API_KEY},
                )
                resp.raise_for_status()
        except Exception as exc:
            log.warning("RAWG get by id %d failed: %s", rawg_id, exc)
            return None

        return self._normalize(resp.json())

    def _normalize(self, raw: dict) -> NormalizedGame:
        platforms = [
            p["platform"]["name"]
            for p in raw.get("platforms") or []
            if isinstance(p, dict) and isinstance(p.get("platform"), dict)
        ]
        genres = [g["name"] for g in raw.get("genres") or [] if isinstance(g, dict)]

        release_date: date | None = None
        released = raw.get("released")
        if released:
            try:
                release_date = date.fromisoformat(released)
            except ValueError:
                pass

        developer: str | None = None
        publisher: str | None = None
        for dev in raw.get("developers") or []:
            if isinstance(dev, dict) and dev.get("name"):
                developer = dev["name"]
                break
        for pub in raw.get("publishers") or []:
            if isinstance(pub, dict) and pub.get("name"):
                publisher = pub["name"]
                break

        metacritic = raw.get("metacritic")
        score = float(metacritic) if metacritic else None
        # RAWG rating is 0–5 scale; normalize to 0–100
        rawg_rating = raw.get("rating")
        rawg_score = round(float(rawg_rating) * 20, 1) if rawg_rating else None

        return NormalizedGame(
            source="RAWG",
            external_id=str(raw.get("id", "")),
            name=raw.get("name", ""),
            external_slug=raw.get("slug"),
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            developer=developer,
            publisher=publisher,
            summary=raw.get("description_raw"),
            cover_url=raw.get("background_image"),
            score=score or rawg_score,
            score_count=int(raw.get("ratings_count") or 0) or None,
            is_critic_score=bool(metacritic),
            raw={
                "rawg_id": raw.get("id"),
                "metacritic": metacritic,
                "rawg_rating": rawg_rating,
                "rawg_score_normalized": rawg_score,
                "playtime": raw.get("playtime"),
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
