"""IGDB Time-To-Beat lookup — an official playtime companion to HLTB.

HLTB is a scrape with no official API; IGDB exposes completion times through its
`game_time_to_beats` endpoint keyed by IGDB game id. Queries are batched because
IGDB accepts up to 500 ids at once.
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
MAX_IGDB_PLAYTIME_BATCH = 500


def _valid_igdb_ids(igdb_ids: list[int]) -> list[int]:
    return sorted({value for value in igdb_ids if isinstance(value, int) and value > 0})[
        :MAX_IGDB_PLAYTIME_BATCH
    ]


def build_igdb_playtime_query(igdb_ids: list[int]) -> str:
    """Build one bounded IGDB query for multiple game ids."""
    valid_ids = _valid_igdb_ids(igdb_ids)
    if not valid_ids:
        return ""
    joined_ids = ",".join(str(value) for value in valid_ids)
    return (
        "fields game_id,normally,hastily,completely; "
        f"where game_id = ({joined_ids}); limit {len(valid_ids)};"
    )


def parse_igdb_playtimes_minutes(rows: object) -> dict[int, int]:
    """Map IGDB game ids to their best available completion time in minutes."""
    if not isinstance(rows, list):
        return {}
    parsed: dict[int, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            game_id = int(row.get("game_id"))
            seconds = int(
                row.get("normally") or row.get("hastily") or row.get("completely")
            )
        except (TypeError, ValueError):
            continue
        if game_id > 0 and seconds > 0:
            parsed[game_id] = seconds // _SECONDS_PER_MINUTE
    return parsed


async def get_igdb_playtimes_minutes(igdb_ids: list[int]) -> dict[int, int] | None:
    """Return per-game completion minutes, or None when the request itself failed."""
    cfg = get_settings()
    body = build_igdb_playtime_query(igdb_ids)
    if not cfg.igdb_configured() or not body:
        return None

    try:
        token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    except Exception:
        log.debug("IGDB token fetch failed for time-to-beat", exc_info=True)
        return None

    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}

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
    return parse_igdb_playtimes_minutes(rows)


async def get_igdb_playtime_minutes(igdb_id: int) -> int | None:
    """Compatibility wrapper for a single IGDB game id."""
    results = await get_igdb_playtimes_minutes([igdb_id])
    return results.get(igdb_id) if results is not None else None
