"""
Steam service adapter.

Handles:
  - App ID lookup by title or slug
  - PC catalog validation
  - Store URL generation
  - App details for entity confirmation

Steam is NOT used for pricing in phase 1 — use ITAD / CheapShark instead.
Steam Web API key (STEAM_WEB_API_KEY) is available but currently optional;
the store search endpoint is public.
"""

import logging
import re
import time

import httpx

from ..config import get_settings
from .steam import STEAM_APP_IDS, _clean_requirement_block, _lookup_steam_app_id  # reuse existing helpers
from .types import NormalizedGame, SourceHealth

log = logging.getLogger(__name__)

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
APP_DETAILS = "https://store.steampowered.com/api/appdetails"
SMOKE_TEST_TITLES = [("portal-2", "Portal 2", 620)]

_STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")


class SteamService:
    def is_configured(self) -> bool:
        return True  # Store search needs no key; Web API key used for extended endpoints

    async def health_check(self) -> SourceHealth:
        try:
            t0 = time.monotonic()
            slug, title, expected_id = SMOKE_TEST_TITLES[0]
            app_id = await self.lookup_app_id(slug, title)
            latency = int((time.monotonic() - t0) * 1000)
            if app_id:
                match = app_id == expected_id
                return SourceHealth(
                    source="steam",
                    configured=get_settings().steam_configured(),
                    working=True,
                    status="ok",
                    message=f"App ID lookup: {app_id} ({'correct' if match else f'expected {expected_id}'})",
                    latency_ms=latency,
                )
            return SourceHealth(
                source="steam",
                configured=get_settings().steam_configured(),
                working=False,
                status="failing",
                message=f"Could not find app ID for test title '{title}'",
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="steam",
                configured=get_settings().steam_configured(),
                working=False,
                status="failing",
                message=f"Steam request failed: {type(exc).__name__}",
            )

    async def lookup_app_id(self, slug: str, title: str) -> int | None:
        # 1. Check hardcoded map first (zero-cost)
        if slug in STEAM_APP_IDS:
            return STEAM_APP_IDS[slug]

        # 2. Try to parse from cover_url or slug string
        for value in (slug,):
            m = _STEAM_APP_ID_RE.search(value)
            if m:
                return int(m.group(1))

        # 3. Store search API
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                return await _lookup_steam_app_id(title, client)
        except Exception as exc:
            log.warning("Steam app ID lookup failed for %r: %s", title, exc)
            return None

    async def get_app_details(self, app_id: int) -> NormalizedGame | None:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    APP_DETAILS,
                    params={"appids": app_id, "cc": "us", "l": "en"},
                )
                resp.raise_for_status()
        except Exception as exc:
            log.warning("Steam app details failed for %d: %s", app_id, exc)
            return None

        data = resp.json()
        app_data = data.get(str(app_id), {})
        if not app_data.get("success"):
            return None

        return self._normalize(app_id, app_data["data"])

    def store_url(self, app_id: int) -> str:
        return f"https://store.steampowered.com/app/{app_id}/"

    def _normalize(self, app_id: int, raw: dict) -> NormalizedGame:
        from datetime import date as _date
        release_date: _date | None = None
        rd = (raw.get("release_date") or {}).get("date")
        if rd:
            from .steam import _parse_steam_release_date
            release_date = _parse_steam_release_date(rd)

        platforms = []
        if raw.get("platforms", {}).get("windows"):
            platforms.append("PC")
        if raw.get("platforms", {}).get("mac"):
            platforms.append("macOS")
        if raw.get("platforms", {}).get("linux"):
            platforms.append("Linux")

        developers = raw.get("developers") or []
        publishers = raw.get("publishers") or []

        genres = [g["description"] for g in raw.get("genres") or [] if isinstance(g, dict)]
        categories = [c["description"] for c in raw.get("categories") or [] if isinstance(c, dict)]
        screenshots = [
            s["path_full"]
            for s in raw.get("screenshots") or []
            if isinstance(s, dict) and s.get("path_full")
        ]
        system_requirements: list[dict[str, str]] = []
        for key, platform in (
            ("pc_requirements", "PC"),
            ("mac_requirements", "Mac"),
            ("linux_requirements", "Linux"),
        ):
            req = raw.get(key) or {}
            if isinstance(req, str):
                minimum = _clean_requirement_block(req)
                recommended = ""
            elif isinstance(req, dict):
                minimum = _clean_requirement_block(req.get("minimum"))
                recommended = _clean_requirement_block(req.get("recommended"))
            else:
                continue
            if minimum or recommended:
                system_requirements.append({
                    "platform": platform,
                    "minimum": minimum,
                    "recommended": recommended,
                })

        return NormalizedGame(
            source="Steam",
            external_id=str(app_id),
            name=raw.get("name", ""),
            external_url=self.store_url(app_id),
            release_date=release_date,
            platforms=platforms,
            genres=genres,
            developer=developers[0] if developers else None,
            publisher=publishers[0] if publishers else None,
            summary=raw.get("short_description"),
            cover_url=raw.get("header_image"),
            raw={
                "steam_app_id": app_id,
                "required_age": raw.get("required_age"),
                "is_free": raw.get("is_free"),
                "categories": categories,
                "metacritic": raw.get("metacritic"),
                "header_image": raw.get("header_image"),
                "website": raw.get("website"),
                "screenshots": screenshots,
                "system_requirements": system_requirements,
                "dlc_ids": [
                    int(item)
                    for item in raw.get("dlc") or []
                    if str(item).isdigit()
                ],
            },
        )


steam_service = SteamService()
