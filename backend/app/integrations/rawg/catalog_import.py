"""Bulk RAWG catalog import: page through /api/games and store new titles."""

from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import Game
from ...services.deduplication import find_existing_duplicate, merge_game_data
from ...services.rawg_import import apply_rawg_metadata, game_from_rawg_list
from ..http_retry import DEFAULT_HEADERS, request_with_retry
from ..rate_limiter import get_rate_limiter
from .client import (
    LIST_TIMEOUT,
    RAWG_LIST_URL,
)
from ..rawg_quota import stop_rawg_requests_if_quota_exhausted
from .persistence import store_rawg_snapshot, upsert_rawg_external_id

log = logging.getLogger(__name__)

_IMPORT_PAGE_DELAY_SECONDS = 0.5
_MAX_CONSECUTIVE_BARREN_PAGES = 3
_NINTENDO_PARENT_PLATFORM_ID = 7


async def import_rawg_games(
    db: Session,
    target: int = 2000,
    page_size: int = 40,
    parent_platform_ids: list[int] | None = None,
) -> dict[str, int]:
    cfg = get_settings()
    if not cfg.rawg_configured():
        raise RuntimeError("RAWG_API_KEY is not configured.")

    imported = 0
    skipped = 0
    page = 1
    consecutive_barren_pages = 0

    async with httpx.AsyncClient(timeout=LIST_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        while imported < target:
            params = _rawg_import_params(
                cfg.RAWG_API_KEY, page, min(page_size, target - imported), parent_platform_ids
            )
            if not await get_rate_limiter().acquire("RAWG"):
                log.info("RAWG import stopped: daily request budget exhausted")
                break
            if page > 1:
                await asyncio.sleep(_IMPORT_PAGE_DELAY_SECONDS)

            results = await _fetch_import_page(client, params)
            if not results:
                break

            page_imported, page_skipped = _store_rawg_import_page(db, results)
            imported += page_imported
            skipped += page_skipped
            db.commit()
            page += 1

            consecutive_barren_pages = 0 if page_imported else consecutive_barren_pages + 1
            if consecutive_barren_pages >= _MAX_CONSECUTIVE_BARREN_PAGES:
                # Once the catalog already holds everything RAWG returns, `imported`
                # stops growing while the loop keeps paging — burning the whole daily
                # budget every run for zero new rows. Stop after a few barren pages.
                log.info(
                    "RAWG import stopped: %d consecutive pages contained no new games",
                    consecutive_barren_pages,
                )
                break

    return {"imported": imported, "skipped": skipped}


async def _fetch_import_page(client: httpx.AsyncClient, params: dict) -> list[dict]:
    response = await request_with_retry(client, "GET", RAWG_LIST_URL, params=params)
    if stop_rawg_requests_if_quota_exhausted(response):
        return []
    if response.status_code in (401, 403):
        raise RuntimeError(
            "RAWG_API_KEY was rejected by RAWG. Add a valid key to backend/.env and restart."
        )
    response.raise_for_status()
    return response.json().get("results", [])


def _rawg_import_params(
    api_key: str,
    page: int,
    page_size: int,
    parent_platform_ids: list[int] | None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "key": api_key,
        "page": page,
        "page_size": page_size,
        "ordering": "-metacritic,-rating",
    }
    if parent_platform_ids:
        params["parent_platforms"] = ",".join(str(pid) for pid in parent_platform_ids)
    return params


def _store_rawg_import_page(db: Session, results: list[dict]) -> tuple[int, int]:
    imported = skipped = 0
    for raw_game in results:
        game = game_from_rawg_list(raw_game)
        existing = _find_existing_game(db, game)
        if existing:
            if apply_rawg_metadata(existing, raw_game):
                db.add(existing)
            merge_game_data(existing, game)
            upsert_rawg_external_id(db, existing, raw_game)
            skipped += 1
            continue

        db.add(game)
        db.flush()
        upsert_rawg_external_id(db, game, raw_game)
        store_rawg_snapshot(
            db,
            endpoint="/api/games",
            query=game.title,
            raw_payload=raw_game,
            rawg_id=str(raw_game.get("id") or ""),
        )
        imported += 1
    return imported, skipped


def _find_existing_game(db: Session, game: Game) -> Game | None:
    existing = db.scalar(select(Game).where(Game.slug == game.slug))
    if existing is None:
        existing = db.scalar(select(Game).where(func.lower(Game.title) == game.title.lower()))
    if existing is None:
        existing = find_existing_duplicate(db, game)
    return existing


async def import_rawg_nintendo_games(db: Session, target: int = 1000, page_size: int = 40) -> dict[str, int]:
    # RAWG parent platform id 7 is Nintendo; it covers Switch and older Nintendo systems.
    return await import_rawg_games(
        db, target=target, page_size=page_size, parent_platform_ids=[_NINTENDO_PARENT_PLATFORM_ID]
    )


async def import_catalog_to_size(db: Session, target_total: int = 10_000) -> dict[str, object]:
    current_total = _game_count(db)
    if current_total >= target_total:
        return {
            "imported": 0,
            "skipped": 0,
            "target_total": target_total,
            "total_games": current_total,
            "sources": {},
        }

    rawg_result = await import_rawg_games(db, target=target_total - current_total)
    return {
        "imported": rawg_result["imported"],
        "skipped": rawg_result["skipped"],
        "target_total": target_total,
        "total_games": _game_count(db),
        "sources": {"RAWG": rawg_result},
    }


def _game_count(db: Session) -> int:
    return db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0
