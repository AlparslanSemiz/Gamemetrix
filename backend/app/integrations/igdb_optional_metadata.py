"""Batched IGDB lookup for sparse, non-blocking website and game-mode fields."""

from __future__ import annotations

import logging
import re

import httpx

from ..config import get_settings
from .http_retry import DEFAULT_HEADERS, request_with_retry
from .igdb import _get_access_token
from .igdb_playtime import MAX_IGDB_PLAYTIME_BATCH
from .steam.identity import steam_identity_verdict
from .igdb_websites import extract_official_website
from .types import normalize_game_modes

log = logging.getLogger(__name__)

_IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
_HTTP_TIMEOUT = 12
_STEAM_CATEGORY = 1
_STEAM_APP_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE)


def build_igdb_optional_metadata_query(igdb_ids: list[int]) -> str:
    valid_ids = sorted({
        value for value in igdb_ids if isinstance(value, int) and value > 0
    })[:MAX_IGDB_PLAYTIME_BATCH]
    if not valid_ids:
        return ""
    joined_ids = ",".join(str(value) for value in valid_ids)
    return (
        "fields id,game_modes.name,websites.url,websites.type,websites.trusted,"
        "external_games.category,external_games.external_game_source,"
        "external_games.uid,external_games.url,external_games.name,external_games.year; "
        f"where id = ({joined_ids}); limit {len(valid_ids)};"
    )


def steam_candidates(raw: dict) -> list[dict[str, object]]:
    """Every Steam cross-reference IGDB lists for a game: app id, product name, year."""
    found: list[dict[str, object]] = []
    for external in raw.get("external_games") or []:
        if not isinstance(external, dict):
            continue
        url = str(external.get("url") or "")
        url_match = _STEAM_APP_URL_RE.search(url)
        is_steam = external.get("category") == _STEAM_CATEGORY or url_match is not None
        if not is_steam:
            continue
        uid = str(external.get("uid") or "").strip()
        candidate = uid if uid.isdigit() else (url_match.group(1) if url_match else "")
        if candidate.isdigit() and int(candidate) > 0:
            year = external.get("year")
            found.append({
                "app_id": int(candidate),
                "name": str(external.get("name") or ""),
                "year": year if isinstance(year, int) else None,
            })
    return found


def pick_steam_app_id(
    candidates: list[dict[str, object]],
    title: str | None,
    release_year: int | None,
) -> int | None:
    """First candidate whose product is this game.

    IGDB lists DLC, soundtracks and sibling products ("Nightreign", "(Retired)")
    as Steam cross-references too. With a title, a named candidate must pass the
    same identity test appdetails would; an unnamed one is accepted and left to
    the Steam id audit.
    """
    for candidate in candidates:
        app_id = candidate["app_id"]
        if not isinstance(app_id, int):
            continue
        name = str(candidate.get("name") or "")
        if not title or not name:
            return app_id
        year = candidate.get("year")
        verdict = steam_identity_verdict(
            title,
            release_year,
            steam_name=name,
            steam_year=year if isinstance(year, int) else None,
        )
        if verdict.ok:
            return app_id
    return None


def extract_steam_app_id(
    raw: dict,
    *,
    title: str | None = None,
    release_year: int | None = None,
) -> int | None:
    return pick_steam_app_id(steam_candidates(raw), title, release_year)


def parse_igdb_optional_metadata(rows: object) -> dict[int, dict[str, object]]:
    if not isinstance(rows, list):
        return {}
    parsed: dict[int, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            igdb_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if igdb_id <= 0:
            continue
        modes = normalize_game_modes([
            str(mode["name"])
            for mode in row.get("game_modes") or []
            if isinstance(mode, dict) and mode.get("name")
        ])
        parsed[igdb_id] = {
            "website": extract_official_website(row),
            "game_modes": modes,
            "steam_candidates": steam_candidates(row),
        }
    return parsed


async def get_igdb_optional_metadata(
    igdb_ids: list[int],
) -> dict[int, dict[str, object]] | None:
    cfg = get_settings()
    body = build_igdb_optional_metadata_query(igdb_ids)
    if not cfg.igdb_configured() or not body:
        return None
    try:
        token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    except Exception:
        log.debug("IGDB token fetch failed for optional metadata", exc_info=True)
        return None

    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=DEFAULT_HEADERS) as client:
            response = await request_with_retry(
                client, "POST", _IGDB_GAMES_URL, headers=headers, content=body
            )
        if not response.is_success:
            return None
        return parse_igdb_optional_metadata(response.json())
    except Exception:
        log.debug("IGDB optional metadata request failed", exc_info=True)
        return None
