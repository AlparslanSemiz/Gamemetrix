"""Field-shape helpers for metadata backfill: URL/cover/requirements validation.

Pure functions plus the "generic placeholder" field markers that both gap
detection and the applier test against.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from ...integrations.title_matching import titles_match
from ...integrations.types import NormalizedGame
from ...models import Game

MAX_SCREENSHOTS = 16
MAX_URL_LENGTH = 500
_EARLIEST_MEANINGFUL_YEAR = 1970

GENERIC_GENRES = {(), ("Uncategorized",), ("Steam",), ("Deal", "PC")}
GENERIC_PLATFORMS = {(), ("Unknown",)}
_PROVIDER_PROFILE_HOSTS = frozenset({
    "gamebrain.co",
    "www.gamebrain.co",
    "igdb.com",
    "www.igdb.com",
    "rawg.io",
    "www.rawg.io",
    "wikidata.org",
    "www.wikidata.org",
})

_PC_REQUIREMENT_PLATFORMS = frozenset({"pc", "steam", "windows"})


def as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def tupled(values: list[str] | None) -> tuple[str, ...]:
    return tuple(values or [])


def titles_match_game(game: Game, candidate: NormalizedGame) -> bool:
    return titles_match(
        game.title,
        candidate.name,
        expected_year=game.release_year if game.release_year > _EARLIEST_MEANINGFUL_YEAR else None,
        candidate_year=candidate.release_date.year if candidate.release_date else None,
    )


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if not url or len(url) > MAX_URL_LENGTH or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    parsed = urlsplit(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return url


def website_needs_repair(value: str | None) -> bool:
    """True when a website is absent, invalid, or just a provider profile."""
    website = safe_url(value)
    if website is None:
        return True
    hostname = (urlsplit(website).hostname or "").lower()
    return hostname in _PROVIDER_PROFILE_HOSTS


def is_missing_cover(value: str | None) -> bool:
    if not value or not value.strip():
        return True
    lowered = value.lower()
    return (
        lowered.startswith("data:image")
        or "placeholder" in lowered
        or lowered in {"none", "null"}
    )


def steam_cover_should_update(current: str | None, app_id: int, fresh: str | None) -> bool:
    if not fresh or not current or current == fresh:
        return False
    return f"/steam/apps/{app_id}/" in current and "store_item_assets" not in current


def system_requirements_need_repair(requirements: list[dict] | None) -> bool:
    if not isinstance(requirements, list) or not requirements:
        return True
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        platform = str(requirement.get("platform") or "").strip().lower()
        if platform not in _PC_REQUIREMENT_PLATFORMS:
            continue
        text = " ".join(
            str(requirement.get(key) or "").strip()
            for key in ("minimum", "recommended")
        )
        if text.strip():
            return False
    return True


def merge_unique(current: list[str] | None, incoming: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in [*(current or []), *incoming]:
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
        if len(merged) >= limit:
            break
    return merged
