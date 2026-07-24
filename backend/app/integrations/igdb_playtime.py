"""IGDB Time-To-Beat lookup — an official playtime fallback for HLTB.

HLTB is a scrape with no official API; IGDB exposes completion times through its
`game_time_to_beats` endpoint keyed by IGDB game id. Used only for games HLTB
could not fill, so the scrape stays the primary source and this never overwrites
an existing playtime.
"""

import logging

import httpx

from ..config import get_settings
from .http_retry import DEFAULT_HEADERS, request_with_retry
from .igdb import _get_access_token

log = logging.getLogger(__name__)

_IGDB_TTB_URL = "https://api.igdb.com/v4/game_time_to_beats"
_HTTP_TIMEOUT = 12
_SECONDS_PER_MINUTE = 60


async def get_igdb_playtime_minutes(igdb_id: int) -> int | None:
    """Main-story completion time in minutes for an IGDB game id, or None."""
    cfg = get_settings()
    if not cfg.igdb_configured() or igdb_id <= 0:
        return None

    try:
        token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    except Exception:
        log.debug("IGDB token fetch failed for time-to-beat", exc_info=True)
        return None

    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    body = f"fields normally,hastily,completely; where game_id = {igdb_id}; limit 1;"

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=DEFAULT_HEADERS) as client:
            response = await request_with_retry(
                client, "POST", _IGDB_TTB_URL, headers=headers, content=body
            )
        if not response.is_success:
            return None
        rows = response.json()
    except Exception:
        log.debug("IGDB time-to-beat request failed", exc_info=True)
        return None

    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    seconds = row.get("normally") or row.get("hastily") or row.get("completely")
    try:
        seconds_int = int(seconds)
    except (TypeError, ValueError):
        return None
    if seconds_int <= 0:
        return None
    return seconds_int // _SECONDS_PER_MINUTE
