"""RAWG quota-response detection shared by every RAWG HTTP client."""

import logging

import httpx

from .rate_limiter import get_rate_limiter


log = logging.getLogger(__name__)


def _rawg_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return " ".join(
        str(payload.get(key) or "")
        for key in ("error", "detail", "message")
    ).casefold()


def stop_rawg_requests_if_quota_exhausted(response: httpx.Response) -> bool:
    """Stop this process from spending more RAWG calls after a quota response.

    RAWG currently reports an exhausted monthly allowance as HTTP 401, the same
    status commonly used for an invalid key. Only the provider's explicit quota
    message (or HTTP 429) trips the circuit, so a genuinely bad key remains
    distinguishable in health diagnostics.
    """
    quota_message = _rawg_error_text(response)
    exhausted = response.status_code == 429 or (
        response.status_code in {401, 403}
        and any(
            marker in quota_message
            for marker in ("limit reached", "quota", "rate limit")
        )
    )
    if not exhausted:
        return False
    get_rate_limiter().set_limit("RAWG", 0)
    log.warning(
        "RAWG quota is exhausted (HTTP %d); disabling further RAWG calls in this process",
        response.status_code,
    )
    return True
