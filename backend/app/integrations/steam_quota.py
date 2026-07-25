"""Steam rate-limit circuit shared by Store and Web API clients."""

import logging
from email.utils import parsedate_to_datetime
from datetime import UTC, datetime

import httpx

from .rate_limiter import get_rate_limiter


log = logging.getLogger(__name__)
_DEFAULT_COOLDOWN_SECONDS = 60 * 60


def _retry_after_seconds(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return _DEFAULT_COOLDOWN_SECONDS
    try:
        return max(1, int(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return _DEFAULT_COOLDOWN_SECONDS
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(1, int((retry_at - datetime.now(UTC)).total_seconds()))


def stop_steam_requests_if_rate_limited(response: httpx.Response) -> bool:
    """Disable more Steam calls in this process after an HTTP 429."""
    if response.status_code != 429:
        return False
    cooldown = _retry_after_seconds(response)
    get_rate_limiter().block("Steam", cooldown)
    log.warning(
        "Steam rate limit reached (HTTP 429); pausing Steam calls for %d seconds",
        cooldown,
    )
    return True
