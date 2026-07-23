"""Per-game RAWG enrichment: resolve the RAWG id, then pull detail + relations."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import ExternalId, Game
from ...services.rawg_import import apply_rawg_metadata, apply_rawg_related
from ..http_retry import DEFAULT_HEADERS
from .client import DETAIL_TIMEOUT, RAWG_LIST_URL, budgeted_rawg_get
from .matching import rawg_candidate_matches
from .persistence import store_rawg_snapshot, upsert_rawg_external_id

_SEARCH_PAGE_SIZE = 5
_RELATED_PAGE_SIZE = 12


async def enrich_rawg_game_detail(db: Session, game: Game) -> bool:
    cfg = get_settings()
    if not cfg.rawg_configured():
        return False

    changed = False
    rawg_id = _extract_rawg_id(game, db)
    async with httpx.AsyncClient(timeout=DETAIL_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        if not rawg_id:
            rawg_id = await _search_rawg_id(client, db, game, cfg.RAWG_API_KEY)
            if not rawg_id:
                return False

        detail_result = await _fetch_matching_rawg_detail(client, db, game, rawg_id, cfg.RAWG_API_KEY)
        if detail_result is None:
            return False
        rawg_id, detail, detail_response = detail_result
        if detail is not None:
            changed = apply_rawg_metadata(game, detail) or changed
            upsert_rawg_external_id(db, game, detail)
            store_rawg_snapshot(
                db,
                endpoint=f"/api/games/{rawg_id}",
                query=game.title,
                raw_payload=detail,
                status_code=detail_response.status_code,
                rawg_id=rawg_id,
            )

        additions = await _fetch_rawg_related(client, db, game, rawg_id, cfg.RAWG_API_KEY, "additions")
        similar = await _fetch_rawg_related(client, db, game, rawg_id, cfg.RAWG_API_KEY, "game-series")

    changed = apply_rawg_related(game, additions, similar) or changed
    game.metadata_refreshed_at = datetime.now(UTC)
    db.add(game)
    db.commit()
    db.refresh(game)
    return changed


def _extract_rawg_id(game: Game, db: Session) -> str | None:
    external = db.scalar(
        select(ExternalId).where(ExternalId.game_id == game.id, ExternalId.source == "RAWG")
    )
    if external:
        return external.external_id
    suffix = game.slug.rsplit("-", 1)[-1]
    return suffix if suffix.isdigit() else None


async def _search_rawg_id(
    client: httpx.AsyncClient,
    db: Session,
    game: Game,
    api_key: str,
) -> str | None:
    search_payload: dict | None = None
    search_status = 200
    matched: dict | None = None
    for exact in (True, False):
        params = {"key": api_key, "search": game.title, "page_size": _SEARCH_PAGE_SIZE}
        if exact:
            params["search_exact"] = "true"
        response = await budgeted_rawg_get(client, RAWG_LIST_URL, params=params)
        if response is None or not response.is_success:
            continue
        search_payload = response.json()
        search_status = response.status_code
        matched = next(
            (item for item in search_payload.get("results") or [] if rawg_candidate_matches(game, item)),
            None,
        )
        if matched:
            break

    if not matched:
        return None
    rawg_id = str(matched.get("id") or "")
    if not rawg_id:
        return None
    upsert_rawg_external_id(db, game, matched)
    store_rawg_snapshot(
        db,
        endpoint="/api/games",
        query=game.title,
        raw_payload=search_payload or {},
        status_code=search_status,
        rawg_id=rawg_id,
    )
    return rawg_id


async def _fetch_matching_rawg_detail(
    client: httpx.AsyncClient,
    db: Session,
    game: Game,
    rawg_id: str,
    api_key: str,
) -> tuple[str, dict | None, httpx.Response] | None:
    response = await budgeted_rawg_get(client, f"{RAWG_LIST_URL}/{rawg_id}", params={"key": api_key})
    if response is None:
        return None
    if not response.is_success:
        return rawg_id, None, response

    detail = response.json()
    if rawg_candidate_matches(game, detail):
        return rawg_id, detail, response

    matched_id = await _search_rawg_id(client, db, game, api_key)
    if not matched_id:
        return None
    response = await budgeted_rawg_get(client, f"{RAWG_LIST_URL}/{matched_id}", params={"key": api_key})
    if response is None or not response.is_success:
        return None
    detail = response.json()
    if not rawg_candidate_matches(game, detail):
        return None
    return matched_id, detail, response


async def _fetch_rawg_related(
    client: httpx.AsyncClient,
    db: Session,
    game: Game,
    rawg_id: str,
    api_key: str,
    relation: str,
) -> list[dict]:
    response = await budgeted_rawg_get(
        client,
        f"{RAWG_LIST_URL}/{rawg_id}/{relation}",
        params={"key": api_key, "page_size": _RELATED_PAGE_SIZE},
    )
    if response is None or not response.is_success:
        return []
    payload = response.json()
    store_rawg_snapshot(
        db,
        endpoint=f"/api/games/{rawg_id}/{relation}",
        query=game.title,
        raw_payload=payload,
        status_code=response.status_code,
        rawg_id=rawg_id,
    )
    return payload.get("results", [])
