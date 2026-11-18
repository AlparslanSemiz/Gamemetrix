"""ProtonDB report summaries: the Proton compatibility tier for one Steam app.

Thin HTTP client. protondb.com publishes no documented quota, so callers must stay
at or below one request per second (see services/protondb_refresh.py).
"""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from .http_retry import DEFAULT_HEADERS

log = logging.getLogger(__name__)

SUMMARY_URL = "https://www.protondb.com/api/v1/reports/summaries/{app_id}.json"
_TIMEOUT_SECONDS = 10
_KNOWN_TIERS = frozenset({"borked", "bronze", "silver", "gold", "platinum", "native"})


@dataclass(frozen=True)
class ProtonSummary:
    """`status`: ok (tier known), no_reports (404 / pending), error (retry later)."""

    status: Literal["ok", "no_reports", "error"]
    tier: str | None = None
    score: float | None = None


def parse_summary(payload: object) -> ProtonSummary:
    if not isinstance(payload, dict):
        return ProtonSummary("error")
    tier = str(payload.get("tier") or "").strip().lower()
    if tier not in _KNOWN_TIERS:
        return ProtonSummary("no_reports")  # "pending" and anything unrecognised
    raw_score = payload.get("score")
    score = float(raw_score) if isinstance(raw_score, (int, float)) and 0 <= raw_score <= 1 else None
    return ProtonSummary("ok", tier=tier, score=score)


async def fetch_proton_summary(app_id: int, client: httpx.AsyncClient) -> ProtonSummary:
    try:
        response = await client.get(
            SUMMARY_URL.format(app_id=app_id), headers=DEFAULT_HEADERS, timeout=_TIMEOUT_SECONDS
        )
    except httpx.HTTPError:
        return ProtonSummary("error")
    if response.status_code == 404:
        return ProtonSummary("no_reports")
    if not response.is_success:
        log.warning("ProtonDB returned HTTP %s for app %s", response.status_code, app_id)
        return ProtonSummary("error")
    try:
        return parse_summary(response.json())
    except ValueError:
        return ProtonSummary("error")
