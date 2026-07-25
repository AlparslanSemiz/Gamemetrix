"""Resumable import from Steam's official IStoreService app catalog."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..content_type import infer_content_type
from ..models import CatalogSyncState, ExternalId, Game
from ..services.deduplication import find_existing_duplicate
from ..services.metadata_backfill.apply import apply_normalized_game
from ..services.metadata_backfill.persistence import upsert_external_id
from ..services.metadata_backfill.sanitize import safe_url
from .rate_limiter import get_rate_limiter
from .steam_service import steam_service
from .steam_quota import stop_steam_requests_if_rate_limited
from .sync import compute_rank_fields


STEAM_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
_STATE_SOURCE = "Steam:official-catalog"
_HTTP_TIMEOUT = 20


@dataclass(frozen=True)
class SteamCatalogPage:
    apps: list[tuple[int, str, int | None]]
    have_more: bool
    last_appid: int


def catalog_request_input(*, last_appid: int = 0, max_results: int = 500) -> dict[str, object]:
    return {
        "last_appid": max(0, int(last_appid)),
        "max_results": max(1, min(50_000, int(max_results))),
        "include_games": True,
        "include_dlc": False,
        "include_software": False,
        "include_videos": False,
        "include_hardware": False,
    }


def parse_catalog_page(payload: object) -> SteamCatalogPage:
    response = payload.get("response") if isinstance(payload, dict) else {}
    if not isinstance(response, dict):
        response = {}
    apps: list[tuple[int, str, int | None]] = []
    for row in response.get("apps") or []:
        if not isinstance(row, dict):
            continue
        app_id = row.get("appid")
        if not isinstance(app_id, int) or app_id <= 0:
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        modified = row.get("last_modified")
        apps.append((app_id, name[:500], modified if isinstance(modified, int) else None))
    raw_last = response.get("last_appid")
    last_appid = raw_last if isinstance(raw_last, int) and raw_last >= 0 else (apps[-1][0] if apps else 0)
    return SteamCatalogPage(
        apps=apps,
        have_more=bool(response.get("have_more_results")),
        last_appid=last_appid,
    )


def _state(db: Session) -> CatalogSyncState:
    existing = db.scalar(select(CatalogSyncState).where(CatalogSyncState.source == _STATE_SOURCE))
    if existing is not None:
        return existing
    existing = CatalogSyncState(
        source=_STATE_SOURCE,
        cursor={},
        completed=False,
        updated_at=datetime.now(UTC),
    )
    db.add(existing)
    db.flush()
    return existing


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "game"


def _new_game_from_steam(result, app_id: int) -> Game:
    released = result.release_date or date(1970, 1, 1)
    game = Game(
        title=result.name[:160],
        slug=f"{_slugify(result.name)}-steam-{app_id}",
        summary=result.summary or "",
        cover_url=result.cover_url or "",
        release_date=released,
        release_year=released.year,
        official_release_date=released if released.year > 1970 else None,
        metacritic_score=None,
        image_url=result.cover_url,
        website_url=safe_url(
            result.raw.get("website")
            if isinstance(result.raw.get("website"), str)
            else None
        ),
        metrix_score=0.0,
        critic_score=0.0,
        user_score=0.0,
        genres=result.genres or ["Uncategorized"],
        platforms=result.platforms or ["PC"],
        source_scores=[],
        developer=result.developer,
        publisher=result.publisher,
        steam_app_id=app_id,
        game_modes=result.game_modes,
        screenshots=[
            value
            for value in result.raw.get("screenshots", [])
            if isinstance(value, str)
        ],
        system_requirements=[
            value
            for value in result.raw.get("system_requirements", [])
            if isinstance(value, dict)
        ],
    )
    game.content_type = infer_content_type(game)
    game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    return game


def _existing_game(db: Session, app_id: int, candidate: Game) -> Game | None:
    external = db.scalar(
        select(ExternalId).where(
            ExternalId.source == "Steam",
            ExternalId.external_id == str(app_id),
        )
    )
    if external:
        return db.get(Game, external.game_id)
    return (
        db.scalar(select(Game).where(Game.steam_app_id == app_id))
        or db.scalar(select(Game).where(Game.slug == candidate.slug))
        or db.scalar(select(Game).where(func.lower(Game.title) == candidate.title.lower()))
        or find_existing_duplicate(db, candidate)
    )


def _ingest_detail(db: Session, result, app_id: int) -> bool:
    candidate = _new_game_from_steam(result, app_id)
    existing = _existing_game(db, app_id, candidate)
    if existing is None:
        db.add(candidate)
        db.flush()
        game = candidate
        created = True
    else:
        apply_normalized_game(existing, result, trusted=True, prefer_cover=not existing.cover_url)
        existing.steam_app_id = app_id
        db.add(existing)
        db.flush()
        game = existing
        created = False
    upsert_external_id(
        db,
        game.id,
        "Steam",
        str(app_id),
        url=steam_service.store_url(app_id),
        confidence=1.0,
    )
    return created


async def import_steam_official_catalog(
    db: Session,
    target: int = 1000,
    page_size: int = 100,
) -> dict[str, int | bool]:
    """Import official Steam game entries, saving the last processed app ID."""
    cfg = get_settings()
    if not cfg.steam_configured():
        raise RuntimeError("STEAM_WEB_API_KEY is required for the official Steam catalog.")

    sync_state = _state(db)
    last_appid = int((sync_state.cursor or {}).get("last_appid") or 0)
    imported = skipped = examined = 0
    safe_target = max(1, int(target))

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        while imported < safe_target:
            # Reserve one call for each app detail after the list request.
            remaining = get_rate_limiter().remaining("Steam")
            request_size = min(max(1, int(page_size)), safe_target - imported, max(0, remaining - 1))
            if request_size <= 0 or not await get_rate_limiter().acquire("Steam"):
                break
            response = await client.get(
                STEAM_APP_LIST_URL,
                params={
                    "key": cfg.STEAM_WEB_API_KEY,
                    "input_json": json.dumps(
                        catalog_request_input(last_appid=last_appid, max_results=request_size),
                        separators=(",", ":"),
                    ),
                },
            )
            if stop_steam_requests_if_rate_limited(response):
                break
            response.raise_for_status()
            page = parse_catalog_page(response.json())
            if not page.apps:
                cursor_advanced = page.last_appid > last_appid
                if cursor_advanced:
                    last_appid = page.last_appid
                    sync_state.cursor = {"last_appid": last_appid}
                sync_state.completed = not page.have_more
                sync_state.last_success_at = datetime.now(UTC)
                sync_state.updated_at = sync_state.last_success_at
                db.commit()
                if page.have_more and cursor_advanced:
                    continue
                break

            sync_state.completed = False
            for app_id, _name, _modified in page.apps:
                result = await steam_service.get_app_details(app_id)
                if result is None or not result.name.strip():
                    skipped += 1
                elif _ingest_detail(db, result, app_id):
                    imported += 1
                else:
                    skipped += 1
                examined += 1
                last_appid = app_id
                now = datetime.now(UTC)
                sync_state.cursor = {"last_appid": last_appid}
                sync_state.last_success_at = now
                sync_state.updated_at = now
                db.commit()
                if imported >= safe_target or get_rate_limiter().remaining("Steam") <= 0:
                    break

            if get_rate_limiter().remaining("Steam") <= 0:
                break
            if not page.have_more and last_appid >= page.last_appid:
                sync_state.completed = True
                sync_state.updated_at = datetime.now(UTC)
                db.commit()
                break

    return {
        "imported": imported,
        "skipped": skipped,
        "examined": examined,
        "last_appid": last_appid,
        "completed": sync_state.completed,
    }
