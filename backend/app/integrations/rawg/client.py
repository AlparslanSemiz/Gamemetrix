"""RAWG HTTP surface: endpoint constants and the budget-gated GET."""

from __future__ import annotations

import logging

import httpx

from ..http_retry import request_with_retry
from ..rate_limiter import get_rate_limiter
from ..rawg_quota import stop_rawg_requests_if_quota_exhausted

log = logging.getLogger(__name__)

RAWG_LIST_URL = "https://api.rawg.io/api/games"
LIST_TIMEOUT = 20
DETAIL_TIMEOUT = 15


async def budgeted_rawg_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
) -> httpx.Response | None:
    """GET that first spends one RAWG request from the daily budget, or None if exhausted."""
    if not await get_rate_limiter().acquire("RAWG"):
        log.debug("RAWG metadata budget exhausted for %s", url)
        return None
    response = await request_with_retry(client, "GET", url, params=params)
    stop_rawg_requests_if_quota_exhausted(response)
    return response
