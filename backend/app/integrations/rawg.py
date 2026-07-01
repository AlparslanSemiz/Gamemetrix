import logging
import re
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExternalId, Game, SourceSnapshot
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

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        while imported < target:
            params: dict[str, str | int] = {
                "key": cfg.RAWG_API_KEY,
                "page": page,
                "page_size": min(page_size, target - imported),
                "ordering": "-metacritic,-rating",
            }
            if parent_platform_ids:
                params["parent_platforms"] = ",".join(str(platform_id) for platform_id in parent_platform_ids)

            response = await client.get(
                _RAWG_LIST_URL,
                params=params,
            )
            if response.status_code in (401, 403):
                raise RuntimeError("RAWG_API_KEY was rejected by RAWG. Add a valid key to backend/.env and restart.")
            response.raise_for_status()
            results = response.json().get("results", [])

            if not results:
                break

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

            db.commit()
            page += 1

    return {"imported": imported, "skipped": skipped}


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


async def enrich_rawg_game_detail(db: Session, game: Game) -> bool:
    cfg = get_settings()
    if not cfg.rawg_configured():
        return False

    rawg_id = _extract_rawg_id(game, db)

    changed = False
    async def _search_rawg_id(client: httpx.AsyncClient) -> str | None:
        search_payload: dict | None = None
        search_resp_status = 200
        matched: dict | None = None
        for exact in (True, False):
            params = {
                "key": cfg.RAWG_API_KEY,
                "search": game.title,
                "page_size": 5,
            }
            if exact:
                params["search_exact"] = "true"
            search_resp = await client.get(_RAWG_LIST_URL, params=params)
            if not search_resp.is_success:
                continue
            search_payload = search_resp.json()
            search_resp_status = search_resp.status_code
            results = search_payload.get("results") or []
            matched = next(
                (item for item in results if _rawg_candidate_matches(game, item)),
                None,
            )
            if matched:
                break
        if not matched:
            return None
        new_rawg_id = str(matched.get("id") or "")
        if not new_rawg_id:
            return None
        _upsert_rawg_external_id(db, game, matched)
        _store_rawg_snapshot(
            db,
            endpoint="/api/games",
            query=game.title,
            raw_payload=search_payload or {},
            status_code=search_resp_status,
            rawg_id=new_rawg_id,
        )
        return new_rawg_id

    async with httpx.AsyncClient(timeout=_DETAIL_TIMEOUT) as client:
        if not rawg_id:
            rawg_id = await _search_rawg_id(client)
            if not rawg_id:
                return False

        detail_resp = await client.get(
            f"{_RAWG_LIST_URL}/{rawg_id}",
            params={"key": cfg.RAWG_API_KEY},
        )
        if detail_resp.is_success:
            detail = detail_resp.json()
            if not _rawg_candidate_matches(game, detail):
                rawg_id = await _search_rawg_id(client)
                if not rawg_id:
                    return False
                detail_resp = await client.get(
                    f"{_RAWG_LIST_URL}/{rawg_id}",
                    params={"key": cfg.RAWG_API_KEY},
                )
                if not detail_resp.is_success:
                    return False
                detail = detail_resp.json()
                if not _rawg_candidate_matches(game, detail):
                    return False
            changed = apply_rawg_metadata(game, detail) or changed
            _upsert_rawg_external_id(db, game, detail)
            _store_rawg_snapshot(
                db,
                endpoint=f"/api/games/{rawg_id}",
                query=game.title,
                raw_payload=detail,
                status_code=detail_resp.status_code,
                rawg_id=rawg_id,
            )

        additions_resp = await client.get(
            f"{_RAWG_LIST_URL}/{rawg_id}/additions",
            params={"key": cfg.RAWG_API_KEY, "page_size": 12},
        )
        additions = additions_resp.json().get("results", []) if additions_resp.is_success else []
        if additions_resp.is_success:
            _store_rawg_snapshot(
                db,
                endpoint=f"/api/games/{rawg_id}/additions",
                query=game.title,
                raw_payload=additions_resp.json(),
                status_code=additions_resp.status_code,
                rawg_id=rawg_id,
            )

        similar_resp = await client.get(
            f"{_RAWG_LIST_URL}/{rawg_id}/game-series",
            params={"key": cfg.RAWG_API_KEY, "page_size": 12},
        )
        similar = similar_resp.json().get("results", []) if similar_resp.is_success else []
        if similar_resp.is_success:
            _store_rawg_snapshot(
                db,
                endpoint=f"/api/games/{rawg_id}/game-series",
                query=game.title,
                raw_payload=similar_resp.json(),
                status_code=similar_resp.status_code,
                rawg_id=rawg_id,
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
