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
from .igdb import _candidate_year, _get_access_token, escape_igdb_search_text  # reuse existing token cache
from .rate_limiter import get_rate_limiter
from .title_matching import title_match_quality
from .types import NormalizedGame, SourceHealth, bounded_float, bounded_int, normalize_game_modes

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
        if get_rate_limiter().remaining("IGDB") <= 0:
            return SourceHealth(
                source="igdb",
                configured=True,
                working=False,
                status="rate_limited",
                message="Configured IGDB request budget is exhausted",
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

    async def search_game(self, title: str, release_year: int | None = None) -> NormalizedGame | None:
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
            f'search "{escape_igdb_search_text(title)}"; '
            "where version_parent = null; "
            "limit 10;"
        )
        headers = {
            "Client-ID": cfg.IGDB_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        if not await get_rate_limiter().acquire("IGDB"):
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(f"{IGDB_API_BASE}/games", headers=headers, content=body)
                resp.raise_for_status()
        except Exception as exc:
            log.warning("IGDB search failed for %r: %s", title, exc)
            return None

        games = resp.json()
        candidates = [row for row in games if isinstance(row, dict)] if isinstance(games, list) else []
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
        if title_match_quality(
            title,
            str(best.get("name") or ""),
            expected_year=release_year,
            candidate_year=_candidate_year(best),
        ) <= 0:
            return None
        return self._normalize(best)

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
        if not await get_rate_limiter().acquire("IGDB"):
            return None
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
        platforms = [
            str(platform["name"])[:100]
            for platform in raw.get("platforms") or []
            if isinstance(platform, dict) and platform.get("name")
        ]
        genres = [
            str(genre["name"])[:100]
            for genre in raw.get("genres") or []
            if isinstance(genre, dict) and genre.get("name")
        ]
        game_modes = normalize_game_modes([
            str(mode["name"])
            for mode in raw.get("game_modes") or []
            if isinstance(mode, dict) and mode.get("name")
        ])

        developer: str | None = None
        publisher: str | None = None
        for company in raw.get("involved_companies") or []:
            if not isinstance(company, dict):
                continue
            company_data = company.get("company")
            name = company_data.get("name") if isinstance(company_data, dict) else None
            if not name:
                continue
            if company.get("developer") and not developer:
                developer = str(name)[:200]
            if company.get("publisher") and not publisher:
                publisher = str(name)[:200]

        release_date: date | None = None
        ts = raw.get("first_release_date")
        if ts:
            try:
                release_date = datetime.fromtimestamp(int(ts), tz=UTC).date()
            except (TypeError, ValueError, OSError, OverflowError):
                pass

        cover_url: str | None = None
        if raw.get("cover") and isinstance(raw["cover"], dict):
            url = raw["cover"].get("url")
            if isinstance(url, str):
                cover_url = url.replace("//", "https://").replace("t_thumb", "t_cover_big")

        score: float | None = None
        score_count: int | None = None
        for score_key, count_key in (
            ("rating", "rating_count"),
            ("total_rating", "total_rating_count"),
            ("aggregated_rating", "aggregated_rating_count"),
        ):
            candidate = bounded_float(raw.get(score_key), maximum=100.0)
            if candidate is not None:
                score = round(candidate, 1)
                score_count = bounded_int(raw.get(count_key))
                break

        return NormalizedGame(
            source="IGDB",
            external_id=str(raw["id"]),
            name=str(raw.get("name") or "")[:500],
            external_slug=str(raw["slug"])[:200] if raw.get("slug") else None,
            external_url=str(raw["url"])[:500] if raw.get("url") else None,
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            game_modes=game_modes,
            developer=developer,
            publisher=publisher,
            summary=str(raw["summary"])[:20_000] if raw.get("summary") else None,
            cover_url=cover_url,
            score=score,
            score_count=score_count,
            is_critic_score=False,
            raw=raw,
        )


igdb_service = IGDBService()
