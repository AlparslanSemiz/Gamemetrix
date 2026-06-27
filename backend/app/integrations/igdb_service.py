"""
IGDB service adapter.

Wraps the token + query logic from igdb.py into a service class
that also returns NormalizedGame objects for entity resolution.
"""

import logging
import time
from datetime import UTC, date, datetime

import httpx

from ..config import get_settings
from .igdb import _get_access_token  # reuse existing token cache
from .types import NormalizedGame, SourceHealth

log = logging.getLogger(__name__)

IGDB_API_BASE = "https://api.igdb.com/v4"
SMOKE_TEST_TITLE = "Portal 2"


class IGDBService:
    def is_configured(self) -> bool:
        return get_settings().igdb_configured()

    async def health_check(self) -> SourceHealth:
        if not self.is_configured():
            return SourceHealth(
                source="igdb",
                configured=False,
                working=False,
                status="missing",
                message="IGDB_CLIENT_ID and IGDB_CLIENT_SECRET not configured",
            )
        try:
            t0 = time.monotonic()
            game = await self.search_game(SMOKE_TEST_TITLE)
            latency = int((time.monotonic() - t0) * 1000)
            if game:
                return SourceHealth(
                    source="igdb",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f'Test query "{SMOKE_TEST_TITLE}" returned result',
                    latency_ms=latency,
                )
            return SourceHealth(
                source="igdb",
                configured=True,
                working=False,
                status="failing",
                message=f'Test query "{SMOKE_TEST_TITLE}" returned no results',
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="igdb",
                configured=True,
                working=False,
                status="failing",
                message=f"IGDB request failed: {type(exc).__name__}",
            )

    async def search_game(self, title: str) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        try:
            token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
        except Exception as exc:
            log.warning("IGDB token fetch failed: %s", exc)
            return None

        body = (
            "fields id,name,slug,first_release_date,rating,rating_count,"
            "aggregated_rating,aggregated_rating_count,total_rating,"
            "total_rating_count,platforms.name,genres.name,cover.url,"
            "involved_companies.company.name,involved_companies.developer,"
            "involved_companies.publisher,summary,external_games.uid,"
            "external_games.category,url; "
            f'search "{title}"; '
            "where version_parent = null; "
            "limit 3;"
        )
        headers = {
            "Client-ID": cfg.IGDB_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(f"{IGDB_API_BASE}/games", headers=headers, content=body)
                resp.raise_for_status()
        except Exception as exc:
            log.warning("IGDB search failed for %r: %s", title, exc)
            return None

        games = resp.json()
        if not games:
            return None

        return self._normalize(games[0])

    async def get_by_igdb_id(self, igdb_id: int) -> NormalizedGame | None:
        cfg = get_settings()
        if not self.is_configured():
            return None
        try:
            token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
        except Exception as exc:
            log.warning("IGDB token fetch failed: %s", exc)
            return None

        body = (
            "fields id,name,slug,first_release_date,rating,rating_count,"
            "aggregated_rating,aggregated_rating_count,total_rating,"
            "total_rating_count,platforms.name,genres.name,cover.url,"
            "involved_companies.company.name,involved_companies.developer,"
            "involved_companies.publisher,summary,url; "
            f"where id = {igdb_id}; "
            "limit 1;"
        )
        headers = {
            "Client-ID": cfg.IGDB_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(f"{IGDB_API_BASE}/games", headers=headers, content=body)
                resp.raise_for_status()
        except Exception as exc:
            log.warning("IGDB get by id %d failed: %s", igdb_id, exc)
            return None

        games = resp.json()
        return self._normalize(games[0]) if games else None

    def _normalize(self, raw: dict) -> NormalizedGame:
        platforms = [p["name"] for p in raw.get("platforms") or [] if isinstance(p, dict)]
        genres = [g["name"] for g in raw.get("genres") or [] if isinstance(g, dict)]

        developer: str | None = None
        publisher: str | None = None
        for company in raw.get("involved_companies") or []:
            if not isinstance(company, dict):
                continue
            name = (company.get("company") or {}).get("name")
            if not name:
                continue
            if company.get("developer") and not developer:
                developer = name
            if company.get("publisher") and not publisher:
                publisher = name

        release_date: date | None = None
        ts = raw.get("first_release_date")
        if ts:
            try:
                release_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
            except (ValueError, OSError):
                pass

        cover_url: str | None = None
        if raw.get("cover") and isinstance(raw["cover"], dict):
            url = raw["cover"].get("url", "")
            cover_url = url.replace("//", "https://").replace("t_thumb", "t_cover_big")

        score = raw.get("rating") or raw.get("total_rating") or raw.get("aggregated_rating")
        score_count = int(
            raw.get("rating_count")
            or raw.get("total_rating_count")
            or raw.get("aggregated_rating_count")
            or 0
        )

        return NormalizedGame(
            source="IGDB",
            external_id=str(raw["id"]),
            name=raw.get("name", ""),
            external_slug=raw.get("slug"),
            external_url=raw.get("url"),
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            developer=developer,
            publisher=publisher,
            summary=raw.get("summary"),
            cover_url=cover_url,
            score=round(float(score), 1) if score is not None else None,
            score_count=score_count or None,
            is_critic_score=False,
            raw=raw,
        )


igdb_service = IGDBService()
