"""High-throughput IGDB rating lookup for already matched catalog games."""

import logging
from math import isfinite

import httpx

from ..config import get_settings
from .http_retry import DEFAULT_HEADERS, request_with_retry
from .igdb import _get_access_token, _pick_review_count, _pick_score
from .types import ExternalScore

log = logging.getLogger(__name__)

_IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
_HTTP_TIMEOUT = 12
MAX_IGDB_SCORE_BATCH = 500


def _valid_igdb_ids(igdb_ids: list[int]) -> list[int]:
    return sorted({value for value in igdb_ids if isinstance(value, int) and value > 0})[
        :MAX_IGDB_SCORE_BATCH
    ]


def build_igdb_scores_query(igdb_ids: list[int]) -> str:
    valid_ids = _valid_igdb_ids(igdb_ids)
    if not valid_ids:
        return ""
    joined_ids = ",".join(str(value) for value in valid_ids)
    return (
        "fields id,slug,url,rating,rating_count,aggregated_rating,"
        "aggregated_rating_count,total_rating,total_rating_count; "
        f"where id = ({joined_ids}); limit {len(valid_ids)};"
    )


def parse_igdb_scores(rows: object) -> dict[int, ExternalScore]:
    if not isinstance(rows, list):
        return {}
    parsed: dict[int, ExternalScore] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            igdb_id = int(row.get("id"))
            raw_score = _pick_score(row)
            normalized_score = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            continue
        if (
            igdb_id <= 0
            or normalized_score is None
            or not isfinite(normalized_score)
            or not 0 <= normalized_score <= 100
        ):
            continue
        review_count = _pick_review_count(row)
        parsed[igdb_id] = ExternalScore(
            source="IGDB",
            score=round(normalized_score, 1),
            review_count=review_count,
            detail=(
                f"IGDB user rating ({review_count} ratings)"
                if review_count
                else "IGDB user rating"
            ),
            raw={
                "igdb_id": igdb_id,
                "igdb_slug": row.get("slug"),
                "igdb_url": row.get("url"),
                "response": row,
            },
        )
    return parsed


async def get_igdb_scores(igdb_ids: list[int]) -> dict[int, ExternalScore] | None:
    cfg = get_settings()
    body = build_igdb_scores_query(igdb_ids)
    if not cfg.igdb_configured() or not body:
        return None
    try:
        token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
        headers = {
            "Client-ID": cfg.IGDB_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=DEFAULT_HEADERS) as client:
            response = await request_with_retry(
                client,
                "POST",
                _IGDB_GAMES_URL,
                headers=headers,
                content=body,
            )
        if not response.is_success:
            return None
        return parse_igdb_scores(response.json())
    except Exception:
        log.debug("IGDB bulk score request failed", exc_info=True)
        return None
