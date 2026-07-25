"""Steam rate-limit circuit shared by Store and Web API clients."""

import logging

import httpx

from .rate_limiter import get_rate_limiter


log = logging.getLogger(__name__)


def stop_steam_requests_if_rate_limited(response: httpx.Response) -> bool:
    """Disable more Steam calls in this process after an HTTP 429."""
    if response.status_code != 429:
        return False
    get_rate_limiter().set_limit("Steam", 0)
    log.warning(
        "Steam rate limit reached (HTTP 429); disabling further Steam calls in this process"
    )
    return True
