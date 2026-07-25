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
from datetime import date

import httpx

from .rate_limiter import get_rate_limiter
from .steam.parsing import clean_requirement_block, parse_release_date
from .steam.reviews import lookup_steam_app_id
from .steam_quota import stop_steam_requests_if_rate_limited
from .types import NormalizedGame, SourceHealth

log = logging.getLogger(__name__)

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
APP_DETAILS = "https://store.steampowered.com/api/appdetails"
SMOKE_TEST_TITLES = [("portal-2", "Portal 2", 620)]

_STEAM_APP_ID_RE = re.compile(r"(?:steam/apps/|/app/|^|[-_])(\d{3,})(?:/|$)")


def _release_date(raw: dict) -> date | None:
    release_data = raw.get("release_date")
    value = release_data.get("date") if isinstance(release_data, dict) else None
    return parse_release_date(value) if value else None


def _platforms(raw: dict) -> list[str]:
    platform_data = raw.get("platforms") if isinstance(raw.get("platforms"), dict) else {}
    return [
        label
        for key, label in (("windows", "PC"), ("mac", "macOS"), ("linux", "Linux"))
        if platform_data.get(key)
    ]


def _text_values(raw: dict, key: str, limit: int) -> list[str]:
    values = raw.get(key)
    if not isinstance(values, list):
        return []
    return [str(value)[:limit] for value in values if value]


def _descriptions(raw: dict, key: str) -> list[str]:
    values = raw.get(key) or []
    return [
        str(value["description"])[:100]
        for value in values
        if isinstance(value, dict) and value.get("description")
    ]


def _screenshots(raw: dict) -> list[str]:
    return [
        str(screenshot["path_full"])[:500]
        for screenshot in raw.get("screenshots") or []
        if isinstance(screenshot, dict) and screenshot.get("path_full")
    ]


def _system_requirements(raw: dict) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    for key, platform in (
        ("pc_requirements", "PC"),
        ("mac_requirements", "Mac"),
        ("linux_requirements", "Linux"),
    ):
        raw_requirement = raw.get(key) or {}
        if isinstance(raw_requirement, str):
            minimum = clean_requirement_block(raw_requirement)
            recommended = ""
        elif isinstance(raw_requirement, dict):
            minimum = clean_requirement_block(raw_requirement.get("minimum"))
            recommended = clean_requirement_block(raw_requirement.get("recommended"))
        else:
            continue
        if minimum or recommended:
            requirements.append({
                "platform": platform,
                "minimum": minimum,
                "recommended": recommended,
            })
    return requirements


def _dlc_ids(raw: dict) -> list[int]:
    values = raw.get("dlc")
    if not isinstance(values, list):
        return []
    return [int(value) for value in values if str(value).isdigit()]


class SteamService:
    def is_configured(self) -> bool:
        return True  # Store search needs no key; Web API key used for extended endpoints

    async def health_check(self) -> SourceHealth:
        if get_rate_limiter().remaining("Steam") <= 0:
            return SourceHealth(
                source="steam",
                configured=True,
                working=False,
                status="rate_limited",
                message="Configured Steam request budget is exhausted",
            )
        try:
            t0 = time.monotonic()
            _slug, title, expected_id = SMOKE_TEST_TITLES[0]
            game = await self.get_app_details(expected_id)
            latency = int((time.monotonic() - t0) * 1000)
            if game:
                return SourceHealth(
                    source="steam",
                    configured=True,
                    working=True,
                    status="ok",
                    message=f"Steam app details returned {game.name}",
                    latency_ms=latency,
                )
            if get_rate_limiter().remaining("Steam") <= 0:
                return SourceHealth(
                    source="steam",
                    configured=True,
                    working=False,
                    status="rate_limited",
                    message="Steam rate limit reached",
                    latency_ms=latency,
                )
            return SourceHealth(
                source="steam",
                configured=True,
                working=False,
                status="failing",
                message=f"Could not find app ID for test title '{title}'",
                latency_ms=latency,
            )
        except Exception as exc:
            return SourceHealth(
                source="steam",
                configured=True,
                working=False,
                status="failing",
                message=f"Steam request failed: {type(exc).__name__}",
            )

    async def lookup_app_id(self, slug: str, title: str) -> int | None:
        # Callers should pass games.steam_app_id when it is set; this resolves the
        # id for rows that do not have one yet.
        # 1. Parse it out of the slug if it embeds one (zero-cost)
        for value in (slug,):
            m = _STEAM_APP_ID_RE.search(value)
            if m:
                return int(m.group(1))

        # 3. Store search API
        if not await get_rate_limiter().acquire("Steam"):
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                return await lookup_steam_app_id(title, client)
        except Exception as exc:
            log.warning("Steam app ID lookup failed for %r: %s", title, exc)
            return None

    async def get_app_details(self, app_id: int) -> NormalizedGame | None:
        if not await get_rate_limiter().acquire("Steam"):
            return None
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(
                    APP_DETAILS,
                    params={"appids": app_id, "cc": "us", "l": "en"},
                )
                if stop_steam_requests_if_rate_limited(resp):
                    return None
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
        developers = _text_values(raw, "developers", 200)
        publishers = _text_values(raw, "publishers", 200)

        return NormalizedGame(
            source="Steam",
            external_id=str(app_id),
            name=str(raw.get("name") or "")[:500],
            external_url=self.store_url(app_id),
            release_date=_release_date(raw),
            platforms=_platforms(raw),
            genres=_descriptions(raw, "genres"),
            developer=developers[0] if developers else None,
            publisher=publishers[0] if publishers else None,
            summary=str(raw["short_description"])[:20_000] if raw.get("short_description") else None,
            cover_url=str(raw["header_image"])[:500] if raw.get("header_image") else None,
            raw={
                "steam_app_id": app_id,
                "required_age": raw.get("required_age"),
                "is_free": raw.get("is_free"),
                "categories": _descriptions(raw, "categories"),
                "metacritic": raw.get("metacritic"),
                "header_image": raw.get("header_image"),
                "website": raw.get("website"),
                "screenshots": _screenshots(raw),
                "system_requirements": _system_requirements(raw),
                "dlc_ids": _dlc_ids(raw),
            },
        )


steam_service = SteamService()
