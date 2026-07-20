"""
Shared outbound HTTP retry/backoff for integration clients.

Providers throttle (429) and hiccup (5xx). Without a retry the daily refresh
simply loses that game until the next cycle; without a User-Agent some
providers reject the request outright. Both concerns live here so every
integration behaves the same way.

Public API:
  request_with_retry(client, method, url, ...) -> httpx.Response
  DEFAULT_HEADERS
"""

import asyncio
import logging

import httpx

from ..config import USER_AGENT


log = logging.getLogger(__name__)

DEFAULT_HEADERS: dict[str, str] = {"User-Agent": USER_AGENT}

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_FACTOR = 2.0
_BACKOFF_MAX_SECONDS = 30.0
# 429 is deliberately NOT retryable: providers count every attempt against the
# quota, so retrying a throttle multiplies real usage exactly when we are already
# at the limit — and metered plans bill the overage. A 429 returns immediately so
# the caller can record the refusal and back off until the next cycle.
_RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})
_THROTTLED_STATUS_CODE = 429


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Honour an integer Retry-After header; ignore HTTP-date form and unparseable values."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(raw.strip()), _BACKOFF_MAX_SECONDS)
    except ValueError:
        return None


def _backoff_seconds(attempt: int) -> float:
    return min(_BACKOFF_BASE_SECONDS * (_BACKOFF_FACTOR ** attempt), _BACKOFF_MAX_SECONDS)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    json: object | None = None,
    headers: dict[str, str] | None = None,
    content: str | bytes | None = None,
) -> httpx.Response:
    """
    Send one request, retrying only transient server/transport errors.

    A 429 is returned as-is without a retry so a throttled provider is never
    hit again inside the same call. Returns the final response so callers keep
    their existing is_success / raise_for_status handling; the last transport
    error is re-raised.
    """
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_error: httpx.TransportError | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await client.request(
                method,
                url,
                params=params,
                json=json,
                content=content,
                headers=merged_headers,
            )
        except httpx.TransportError as exc:
            last_error = exc
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        if response.status_code == _THROTTLED_STATUS_CODE:
            log.warning("%s %s throttled (HTTP 429) — not retrying to protect the quota", method, url)
            return response

        if response.status_code not in _RETRYABLE_STATUS_CODES or attempt == _MAX_ATTEMPTS - 1:
            return response

        delay = _retry_after_seconds(response) or _backoff_seconds(attempt)
        log.debug(
            "Retrying %s %s after HTTP %s in %.1fs (attempt %d/%d)",
            method,
            url,
            response.status_code,
            delay,
            attempt + 1,
            _MAX_ATTEMPTS,
        )
        await asyncio.sleep(delay)

    # Unreachable: the loop either returns a response or raises.
    raise last_error if last_error else RuntimeError("request_with_retry exhausted without a result")
