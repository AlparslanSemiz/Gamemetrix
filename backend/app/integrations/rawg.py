import asyncio
import logging
import re
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExternalId, Game, SourceSnapshot
from .http_retry import DEFAULT_HEADERS, request_with_retry
from .rate_limiter import get_rate_limiter
from ..services.rawg_import import (
    apply_rawg_metadata,
    apply_rawg_related,
    game_from_rawg_list,
)
from ..services.deduplication import find_existing_duplicate, merge_game_data


log = logging.getLogger(__name__)

_RAWG_LIST_URL = "https://api.rawg.io/api/games"
_HTTP_TIMEOUT = 20
_DETAIL_TIMEOUT = 15
_IMPORT_PAGE_DELAY_SECONDS = 0.5
_MAX_CONSECUTIVE_BARREN_PAGES = 3


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    tokens = {"ii": "2", "iii": "3", "iv": "4"}
    return " ".join(tokens.get(part, part) for part in normalized.split())


def _title_matches(expected: str, candidate: str | None) -> bool:
    expected_norm = _normalize_title(expected)
    candidate_norm = _normalize_title(candidate)
    return bool(expected_norm and candidate_norm and expected_norm == candidate_norm)


def _rawg_candidate_matches(game: Game, raw_game: dict) -> bool:
    if _title_matches(game.title, raw_game.get("name")):
        return True

    expected_norm = _normalize_title(game.title)
    candidate_norm = _normalize_title(raw_game.get("name"))
    released = str(raw_game.get("released") or "")
    release_year = int(released[:4]) if released[:4].isdigit() else None
    expected_without_remake = expected_norm.removesuffix(" remake").strip()
    if (
        expected_norm.endswith(" remake")
        and candidate_norm == expected_without_remake
        and release_year is not None
        and abs(release_year - game.release_year) <= 1
    ):
        return True
    return False


def _rawg_game_url(raw_game: dict) -> str | None:
    slug = raw_game.get("slug")
    return f"https://rawg.io/games/{slug}" if slug else None


def _upsert_rawg_external_id(db: Session, game: Game, raw_game: dict) -> None:
    rawg_id = raw_game.get("id")
    if not rawg_id:
        return
    now = datetime.now(UTC)
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == "RAWG",
        )
    )
    if existing:
        existing.external_id = str(rawg_id)
        existing.external_slug = raw_game.get("slug")
        existing.external_url = _rawg_game_url(raw_game)
        existing.updated_at = now
        return

    db.add(ExternalId(
        game_id=game.id,
        source="RAWG",
        external_id=str(rawg_id),
        external_slug=raw_game.get("slug"),
        external_url=_rawg_game_url(raw_game),
        confidence=0.92,
        is_primary=True,
        created_at=now,
        updated_at=now,
    ))


def _store_rawg_snapshot(
    db: Session,
    endpoint: str,
    query: str,
    raw_payload: dict,
    status_code: int = 200,
    rawg_id: str | None = None,
) -> None:
    now = datetime.now(UTC)
    db.add(SourceSnapshot(
        source="RAWG",
        endpoint=endpoint,
        query=query,
        external_id=rawg_id,
        status_code=status_code,
        raw_payload=raw_payload,
        fetched_at=now,
        created_at=now,
    ))


async def _budgeted_rawg_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
) -> httpx.Response | None:
    if not await get_rate_limiter().acquire("RAWG"):
        log.debug("RAWG metadata budget exhausted for %s", url)
        return None
    return await request_with_retry(client, "GET", url, params=params)


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

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        while imported < target:
            params = _rawg_import_params(
                cfg.RAWG_API_KEY,
                page,
                min(page_size, target - imported),
                parent_platform_ids,
            )

            if not await get_rate_limiter().acquire("RAWG"):
                log.info("RAWG import stopped: daily request budget exhausted")
                break

            if page > 1:
                await asyncio.sleep(_IMPORT_PAGE_DELAY_SECONDS)

            response = await request_with_retry(
                client,
                "GET",
                _RAWG_LIST_URL,
                params=params,
            )
            if response.status_code in (401, 403):
                raise RuntimeError("RAWG_API_KEY was rejected by RAWG. Add a valid key to backend/.env and restart.")
            response.raise_for_status()
            results = response.json().get("results", [])

            if not results:
                break

            page_imported, page_skipped = _store_rawg_import_page(db, results)
            imported += page_imported
            skipped += page_skipped
            db.commit()
            page += 1

            # Once the catalog already holds everything RAWG returns, `imported`
            # stops growing while the loop keeps paging — burning the whole daily
            # budget every run for zero new rows. Stop after a few barren pages.
            if page_imported == 0:
                consecutive_barren_pages += 1
                if consecutive_barren_pages >= _MAX_CONSECUTIVE_BARREN_PAGES:
                    log.info(
                        "RAWG import stopped: %d consecutive pages contained no new games",
                        consecutive_barren_pages,
                    )
                    break
            else:
                consecutive_barren_pages = 0

    return {"imported": imported, "skipped": skipped}


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
        params["parent_platforms"] = ",".join(
            str(platform_id) for platform_id in parent_platform_ids
        )
    return params


def _store_rawg_import_page(db: Session, results: list[dict]) -> tuple[int, int]:
    imported = skipped = 0
    for raw_game in results:
        game = game_from_rawg_list(raw_game)
        existing = db.scalar(select(Game).where(Game.slug == game.slug))
        if existing is None:
            existing = db.scalar(
                select(Game).where(func.lower(Game.title) == game.title.lower())
            )
        if existing is None:
            existing = find_existing_duplicate(db, game)
        if existing:
            if apply_rawg_metadata(existing, raw_game):
                db.add(existing)
            merge_game_data(existing, game)
            _upsert_rawg_external_id(db, existing, raw_game)
            skipped += 1
            continue

        db.add(game)
        db.flush()
        _upsert_rawg_external_id(db, game, raw_game)
        _store_rawg_snapshot(
            db,
            endpoint="/api/games",
            query=game.title,
            raw_payload=raw_game,
            rawg_id=str(raw_game.get("id") or ""),
        )
        imported += 1
    return imported, skipped


async def import_rawg_nintendo_games(db: Session, target: int = 1000, page_size: int = 40) -> dict[str, int]:
    # RAWG parent platform id 7 is Nintendo; it covers Switch and older Nintendo systems.
    return await import_rawg_games(db, target=target, page_size=page_size, parent_platform_ids=[7])


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
    search_resp_status = 200
    matched: dict | None = None
    for exact in (True, False):
        params = {"key": api_key, "search": game.title, "page_size": 5}
        if exact:
            params["search_exact"] = "true"
        response = await _budgeted_rawg_get(client, _RAWG_LIST_URL, params=params)
        if response is None or not response.is_success:
            continue
        search_payload = response.json()
        search_resp_status = response.status_code
        matched = next(
            (
                item
                for item in search_payload.get("results") or []
                if _rawg_candidate_matches(game, item)
            ),
            None,
        )
        if matched:
            break
    if not matched:
        return None
    rawg_id = str(matched.get("id") or "")
    if not rawg_id:
        return None
    _upsert_rawg_external_id(db, game, matched)
    _store_rawg_snapshot(
        db,
        endpoint="/api/games",
        query=game.title,
        raw_payload=search_payload or {},
        status_code=search_resp_status,
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
    response = await _budgeted_rawg_get(
        client,
        f"{_RAWG_LIST_URL}/{rawg_id}",
        params={"key": api_key},
    )
    if response is None:
        return None
    if not response.is_success:
        return rawg_id, None, response

    detail = response.json()
    if _rawg_candidate_matches(game, detail):
        return rawg_id, detail, response
    matched_id = await _search_rawg_id(client, db, game, api_key)
    if not matched_id:
        return None
    response = await _budgeted_rawg_get(
        client,
        f"{_RAWG_LIST_URL}/{matched_id}",
        params={"key": api_key},
    )
    if response is None or not response.is_success:
        return None
    detail = response.json()
    if not _rawg_candidate_matches(game, detail):
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
    response = await _budgeted_rawg_get(
        client,
        f"{_RAWG_LIST_URL}/{rawg_id}/{relation}",
        params={"key": api_key, "page_size": 12},
    )
    if response is None or not response.is_success:
        return []
    payload = response.json()
    _store_rawg_snapshot(
        db,
        endpoint=f"/api/games/{rawg_id}/{relation}",
        query=game.title,
        raw_payload=payload,
        status_code=response.status_code,
        rawg_id=rawg_id,
    )
    return payload.get("results", [])


async def enrich_rawg_game_detail(db: Session, game: Game) -> bool:
    cfg = get_settings()
    if not cfg.rawg_configured():
        return False

    changed = False
    rawg_id = _extract_rawg_id(game, db)
    async with httpx.AsyncClient(timeout=_DETAIL_TIMEOUT, headers=DEFAULT_HEADERS) as client:
        if not rawg_id:
            rawg_id = await _search_rawg_id(client, db, game, cfg.RAWG_API_KEY)
            if not rawg_id:
                return False

        detail_result = await _fetch_matching_rawg_detail(
            client,
            db,
            game,
            rawg_id,
            cfg.RAWG_API_KEY,
        )
        if detail_result is None:
            return False
        rawg_id, detail, detail_response = detail_result
        if detail is not None:
            changed = apply_rawg_metadata(game, detail) or changed
            _upsert_rawg_external_id(db, game, detail)
            _store_rawg_snapshot(
                db,
                endpoint=f"/api/games/{rawg_id}",
                query=game.title,
                raw_payload=detail,
                status_code=detail_response.status_code,
                rawg_id=rawg_id,
            )

        additions = await _fetch_rawg_related(
            client,
            db,
            game,
            rawg_id,
            cfg.RAWG_API_KEY,
            "additions",
        )
        similar = await _fetch_rawg_related(
            client,
            db,
            game,
            rawg_id,
            cfg.RAWG_API_KEY,
            "game-series",
        )

    changed = apply_rawg_related(game, additions, similar) or changed
    game.metadata_refreshed_at = datetime.now(UTC)
    db.add(game)
    db.commit()
    db.refresh(game)
    return changed


async def import_catalog_to_size(db: Session, target_total: int = 10_000) -> dict[str, object]:
    current_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0
    if current_total >= target_total:
        return {
            "imported": 0,
            "skipped": 0,
            "target_total": target_total,
            "total_games": current_total,
            "sources": {},
        }

    needed = target_total - current_total
    rawg_result = await import_rawg_games(db, target=needed)
    new_total = db.scalar(select(func.count(Game.id)).where(Game.content_type == "game")) or 0
    return {
        "imported": rawg_result["imported"],
        "skipped": rawg_result["skipped"],
        "target_total": target_total,
        "total_games": new_total,
        "sources": {"RAWG": rawg_result},
    }
