import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..content_type import infer_content_type
from ..models import CatalogSyncState, ExternalId, Game
from ..services.deduplication import (
    DuplicateCandidateIndex,
    add_duplicate_candidate,
    build_duplicate_candidate_index,
    find_existing_duplicate,
    merge_game_data,
)
from ..services.rawg_import import platform_family
from .rate_limiter import get_rate_limiter
from .igdb import _get_access_token
from .sync import calculate_metrix_score, compute_rank_fields


IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
NINTENDO_PLATFORM_IDS = [
    130,  # Nintendo Switch
    508,  # Nintendo Switch 2
    41,   # Wii U
    5,    # Wii
    37,   # Nintendo 3DS
    137,  # New Nintendo 3DS
    20,   # Nintendo DS
    159,  # Nintendo DSi
    21,   # Nintendo GameCube
    4,    # Nintendo 64
    19,   # SNES
    18,   # NES
    24,   # Game Boy Advance
    22,   # Game Boy Color
    33,   # Game Boy
]
_HTTP_TIMEOUT = 20
_TITLE_MAX_LENGTH = 160
_SLUG_MAX_LENGTH = 180
_COMPANY_MAX_LENGTH = 200
_EXTERNAL_SLUG_MAX_LENGTH = 200
_URL_MAX_LENGTH = 500


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "game"


def _igdb_image_url(url: str | None, size: str) -> str | None:
    if not url:
        return None
    return url.replace("//", "https://").replace("t_thumb", size)


def _igdb_date(timestamp: int | None) -> date:
    if not timestamp:
        return date(1970, 1, 1)
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).date()
    except (OSError, ValueError):
        return date(1970, 1, 1)


def _company_names(raw_game: dict) -> tuple[str | None, str | None]:
    developer: str | None = None
    publisher: str | None = None
    for item in raw_game.get("involved_companies") or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("company") or {}).get("name")
        if not name:
            continue
        if item.get("developer") and not developer:
            developer = str(name)[:_COMPANY_MAX_LENGTH]
        if item.get("publisher") and not publisher:
            publisher = str(name)[:_COMPANY_MAX_LENGTH]
    return developer, publisher


def _score_fields(raw_game: dict) -> tuple[float, int, float, float]:
    user_score = float(raw_game.get("rating") or raw_game.get("total_rating") or raw_game.get("aggregated_rating") or 0)
    critic_score = float(raw_game.get("aggregated_rating") or raw_game.get("total_rating") or raw_game.get("rating") or 0)
    review_count = int(
        raw_game.get("rating_count")
        or raw_game.get("total_rating_count")
        or raw_game.get("aggregated_rating_count")
        or 0
    )
    score = float(raw_game.get("total_rating") or raw_game.get("rating") or raw_game.get("aggregated_rating") or 0)
    return score, review_count, critic_score, user_score


def _game_from_igdb(
    raw_game: dict,
    *,
    catalog_label: str = "IGDB",
    default_platforms: list[str] | None = None,
) -> Game:
    raw_title = str(raw_game.get("name") or "Untitled Game").strip() or "Untitled Game"
    title = raw_title[:_TITLE_MAX_LENGTH]
    slug_suffix = str(raw_game.get("id") or "game")
    slug_base_limit = max(1, _SLUG_MAX_LENGTH - len(slug_suffix) - 1)
    slug = f"{_slugify(raw_title)[:slug_base_limit]}-{slug_suffix}"[:_SLUG_MAX_LENGTH]
    released = _igdb_date(raw_game.get("first_release_date"))
    cover_url = (
        _igdb_image_url((raw_game.get("cover") or {}).get("url"), "t_cover_big_2x") or ""
    )[:_URL_MAX_LENGTH]
    screenshots = [
        url[:_URL_MAX_LENGTH]
        for item in raw_game.get("screenshots") or []
        if (url := _igdb_image_url(item.get("url") if isinstance(item, dict) else None, "t_screenshot_big"))
    ]
    genres = [
        item["name"]
        for item in raw_game.get("genres") or []
        if isinstance(item, dict) and item.get("name")
    ]
    platforms = sorted({
        platform_family(item["name"])
        for item in raw_game.get("platforms") or []
        if isinstance(item, dict) and item.get("name")
    })
    developer, publisher = _company_names(raw_game)
    score, review_count, critic_score, user_score = _score_fields(raw_game)
    source_scores = []
    if score > 0:
        source_scores.append({
            "source": "IGDB",
            "score": round(score, 1),
            "scale": 100,
            "status": "live",
            "review_count": review_count,
            "detail": f"IGDB total rating from {catalog_label} catalog import.",
        })
    metrix_score = calculate_metrix_score(source_scores)
    game = Game(
        title=title,
        slug=slug,
        # Never manufacture an "about" paragraph. Empty summaries are explicitly
        # picked up by the metadata/quality backfills.
        summary=raw_game.get("summary") or "",
        cover_url=cover_url,
        release_date=released,
        release_year=released.year,
        official_release_date=released if released.year > 1970 else None,
        metacritic_score=None,
        image_url=cover_url or None,
        metrix_score=metrix_score,
        critic_score=critic_score,
        user_score=user_score,
        genres=genres or ["Uncategorized"],
        platforms=platforms or (default_platforms or ["Uncategorized"]),
        source_scores=source_scores,
        developer=developer,
        publisher=publisher,
        screenshots=screenshots,
    )
    game.content_type = infer_content_type(game)
    game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    return game


@dataclass
class _IGDBCatalogLookup:
    game_ids_by_igdb_id: dict[str, int]
    game_ids_by_slug: dict[str, int]
    game_ids_by_lower_title: dict[str, int]
    external_ids_by_game_id: dict[int, tuple[int, str]]
    duplicate_candidates: DuplicateCandidateIndex


def _build_igdb_catalog_lookup(db: Session) -> _IGDBCatalogLookup:
    by_game_id: dict[int, tuple[int, str]] = {}
    by_igdb_id: dict[str, int] = {}
    external_ids = db.execute(
        select(
            ExternalId.id,
            ExternalId.game_id,
            ExternalId.external_id,
        )
        .where(ExternalId.source == "IGDB")
        .order_by(ExternalId.id)
        .execution_options(yield_per=1000)
    )
    for external_id, game_id, external_value in external_ids:
        by_game_id.setdefault(game_id, (external_id, external_value))
        if external_value:
            by_igdb_id.setdefault(external_value, game_id)

    by_slug: dict[str, int] = {}
    by_lower_title: dict[str, int] = {}
    game_rows = db.execute(
        select(Game.id, Game.slug, Game.title)
        .order_by(Game.id)
        .execution_options(yield_per=1000)
    )
    for row in game_rows:
        by_slug.setdefault(row.slug, row.id)
        by_lower_title.setdefault(row.title.lower(), row.id)
    return _IGDBCatalogLookup(
        game_ids_by_igdb_id=by_igdb_id,
        game_ids_by_slug=by_slug,
        game_ids_by_lower_title=by_lower_title,
        external_ids_by_game_id=by_game_id,
        duplicate_candidates=build_duplicate_candidate_index(db),
    )


def _upsert_igdb_external_id(
    db: Session,
    game: Game,
    raw_game: dict,
    *,
    lookup: _IGDBCatalogLookup | None = None,
) -> None:
    igdb_id = str(raw_game.get("id") or "")
    if not igdb_id:
        return
    now = datetime.now(UTC)
    existing = (
        db.get(ExternalId, lookup.external_ids_by_game_id[game.id][0])
        if lookup is not None and game.id in lookup.external_ids_by_game_id
        else None
    )
    if lookup is None:
        existing = (
            db.scalar(
                select(ExternalId).where(
                    ExternalId.game_id == game.id,
                    ExternalId.source == "IGDB",
                )
            )
        )
    if existing:
        old_external_id = existing.external_id
        existing.external_id = igdb_id
        existing.external_slug = (
            str(raw_game["slug"])[:_EXTERNAL_SLUG_MAX_LENGTH]
            if raw_game.get("slug")
            else None
        )
        existing.external_url = (
            str(raw_game["url"])[:_URL_MAX_LENGTH] if raw_game.get("url") else None
        )
        existing.updated_at = now
        if lookup is not None:
            if lookup.game_ids_by_igdb_id.get(old_external_id) == game.id:
                lookup.game_ids_by_igdb_id.pop(old_external_id, None)
            lookup.game_ids_by_igdb_id[igdb_id] = game.id
        return
    external = ExternalId(
        game_id=game.id,
        source="IGDB",
        external_id=igdb_id,
        external_slug=(
            str(raw_game["slug"])[:_EXTERNAL_SLUG_MAX_LENGTH]
            if raw_game.get("slug")
            else None
        ),
        external_url=(
            str(raw_game["url"])[:_URL_MAX_LENGTH] if raw_game.get("url") else None
        ),
        confidence=0.9,
        is_primary=True,
        created_at=now,
        updated_at=now,
    )
    db.add(external)
    db.flush()
    if lookup is not None:
        lookup.external_ids_by_game_id[game.id] = (external.id, igdb_id)
        lookup.game_ids_by_igdb_id[igdb_id] = game.id


def _existing_by_igdb_id(
    db: Session,
    raw_game: dict,
    *,
    lookup: _IGDBCatalogLookup | None = None,
) -> Game | None:
    igdb_id = str(raw_game.get("id") or "")
    if not igdb_id:
        return None
    if lookup is not None:
        game_id = lookup.game_ids_by_igdb_id.get(igdb_id)
        return db.get(Game, game_id) if game_id is not None else None
    external = db.scalar(
        select(ExternalId).where(
            ExternalId.source == "IGDB",
            ExternalId.external_id == igdb_id,
        )
    )
    return db.get(Game, external.game_id) if external else None


def _existing_igdb_game(
    db: Session,
    raw_game: dict,
    candidate: Game,
    lookup: _IGDBCatalogLookup | None,
) -> Game | None:
    existing = _existing_by_igdb_id(db, raw_game, lookup=lookup)
    if existing is not None:
        return existing
    if lookup is not None:
        game_id = (
            lookup.game_ids_by_slug.get(candidate.slug)
            or lookup.game_ids_by_lower_title.get(candidate.title.lower())
        )
        existing = db.get(Game, game_id) if game_id is not None else None
    else:
        existing = (
            db.scalar(select(Game).where(Game.slug == candidate.slug))
            or db.scalar(
                select(Game).where(func.lower(Game.title) == candidate.title.lower())
            )
        )
    return existing or find_existing_duplicate(
        db,
        candidate,
        candidate_index=lookup.duplicate_candidates if lookup is not None else None,
    )


_IGDB_CREDENTIALS_REJECTED = (
    "IGDB credentials were rejected. Add valid Twitch/IGDB credentials to backend/.env and restart."
)
_IGDB_IMPORT_FIELDS = (
    "fields id,name,slug,url,game_type,first_release_date,rating,rating_count,"
    "aggregated_rating,aggregated_rating_count,total_rating,total_rating_count,"
    "platforms.name,genres.name,cover.url,screenshots.url,summary,"
    "involved_companies.company.name,involved_companies.developer,"
    "involved_companies.publisher; "
)
# Global popular-catalog quality gate: main games only, with enough
# rated reviews to be worth ranking. Keeps the general import from flooding the
# catalog with the hundreds of thousands of obscure IGDB entries.
_GENERAL_MIN_RATING_COUNT = 8
_MAIN_GAME_TYPE = 0
_FULL_CATALOG_STATE = "IGDB:full-catalog"


def build_full_catalog_query(*, after_id: int, page_size: int = 500) -> str:
    """Build a stable, keyset-paginated IGDB query for every main game."""
    safe_after_id = max(0, int(after_id))
    safe_page_size = max(1, min(500, int(page_size)))
    return (
        _IGDB_IMPORT_FIELDS
        + f"where id > {safe_after_id} & version_parent = null & game_type = {_MAIN_GAME_TYPE}; "
        + "sort id asc; "
        + f"limit {safe_page_size};"
    )


def _catalog_state(db: Session, source: str) -> CatalogSyncState:
    state = db.scalar(select(CatalogSyncState).where(CatalogSyncState.source == source))
    if state is not None:
        return state
    state = CatalogSyncState(
        source=source,
        cursor={},
        completed=False,
        updated_at=datetime.now(UTC),
    )
    db.add(state)
    db.flush()
    return state


async def _igdb_token_or_raise(cfg) -> str:
    try:
        return await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise RuntimeError(_IGDB_CREDENTIALS_REJECTED) from exc
        raise


def _ingest_igdb_game(
    db: Session,
    raw_game: dict,
    *,
    catalog_label: str,
    default_platforms: list[str] | None,
    lookup: _IGDBCatalogLookup | None = None,
) -> bool:
    """Create or merge one IGDB game. Returns True when a new row was created."""
    game = _game_from_igdb(raw_game, catalog_label=catalog_label, default_platforms=default_platforms)
    existing = _existing_igdb_game(db, raw_game, game, lookup)
    if existing:
        merge_game_data(existing, game)
        db.add(existing)
        _upsert_igdb_external_id(db, existing, raw_game, lookup=lookup)
        if lookup is not None:
            lookup.game_ids_by_slug.setdefault(game.slug, existing.id)
            lookup.game_ids_by_lower_title.setdefault(game.title.lower(), existing.id)
        return False
    db.add(game)
    db.flush()
    _upsert_igdb_external_id(db, game, raw_game, lookup=lookup)
    if lookup is not None:
        lookup.game_ids_by_slug[game.slug] = game.id
        lookup.game_ids_by_lower_title.setdefault(game.title.lower(), game.id)
        add_duplicate_candidate(lookup.duplicate_candidates, game)
    return True


async def import_igdb_nintendo_games(db: Session, target: int = 500, page_size: int = 50) -> dict[str, int]:
    cfg = get_settings()
    if not cfg.igdb_configured():
        raise RuntimeError("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are not configured.")

    token = await _igdb_token_or_raise(cfg)
    imported = 0
    skipped = 0
    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    lookup = _build_igdb_catalog_lookup(db)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for platform_id in NINTENDO_PLATFORM_IDS:
            offset = 0
            while imported < target:
                body = (
                    _IGDB_IMPORT_FIELDS +
                    f"where platforms = {platform_id} & version_parent = null "
                    f"& game_type = {_MAIN_GAME_TYPE} & total_rating_count > 0; "
                    "sort total_rating_count desc; "
                    f"limit {min(page_size, target - imported)}; offset {offset};"
                )
                if not await get_rate_limiter().acquire("IGDB"):
                    break
                response = await client.post(IGDB_GAMES_URL, headers=headers, content=body)
                if response.status_code in (401, 403):
                    raise RuntimeError(_IGDB_CREDENTIALS_REJECTED)
                response.raise_for_status()
                results = response.json()
                if not results:
                    break

                for raw_game in results:
                    if _ingest_igdb_game(
                        db,
                        raw_game,
                        catalog_label="Nintendo",
                        default_platforms=["Nintendo"],
                        lookup=lookup,
                    ):
                        imported += 1
                    else:
                        skipped += 1

                db.commit()
                offset += page_size
                if len(results) < page_size:
                    break
            if imported >= target:
                break

    return {"imported": imported, "skipped": skipped}


async def import_igdb_popular_games(db: Session, target: int = 1000, page_size: int = 50) -> dict[str, int]:
    """Import the most-rated games across every platform (RAWG-free catalog growth).

    Additive to the RAWG catalog import: reuses IGDB's generous budget to grow the
    catalog so RAWG's scarce monthly quota can go to Metacritic lookups instead.
    """
    cfg = get_settings()
    if not cfg.igdb_configured():
        raise RuntimeError("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are not configured.")

    token = await _igdb_token_or_raise(cfg)
    imported = 0
    skipped = 0
    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    offset = 0
    lookup = _build_igdb_catalog_lookup(db)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        while imported < target:
            body = (
                _IGDB_IMPORT_FIELDS +
                f"where total_rating_count >= {_GENERAL_MIN_RATING_COUNT} "
                f"& version_parent = null & game_type = {_MAIN_GAME_TYPE}; "
                "sort total_rating_count desc; "
                f"limit {min(page_size, target - imported)}; offset {offset};"
            )
            if not await get_rate_limiter().acquire("IGDB"):
                break
            response = await client.post(IGDB_GAMES_URL, headers=headers, content=body)
            if response.status_code in (401, 403):
                raise RuntimeError(_IGDB_CREDENTIALS_REJECTED)
            response.raise_for_status()
            results = response.json()
            if not results:
                break

            for raw_game in results:
                if _ingest_igdb_game(
                    db,
                    raw_game,
                    catalog_label="popular",
                    default_platforms=None,
                    lookup=lookup,
                ):
                    imported += 1
                else:
                    skipped += 1

            db.commit()
            offset += page_size
            if len(results) < page_size:
                break

    return {"imported": imported, "skipped": skipped}


async def import_igdb_full_catalog(
    db: Session,
    target: int = 5000,
    page_size: int = 500,
) -> dict[str, int | bool]:
    """Resume a complete main-game scan without rating/popularity filtering."""
    cfg = get_settings()
    if not cfg.igdb_configured():
        raise RuntimeError("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are not configured.")

    token = await _igdb_token_or_raise(cfg)
    state = _catalog_state(db, _FULL_CATALOG_STATE)
    after_id = int((state.cursor or {}).get("after_id") or 0)
    imported = skipped = examined = 0
    safe_target = max(1, int(target))
    safe_page_size = max(1, min(500, int(page_size)))
    headers = {"Client-ID": cfg.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
    lookup = _build_igdb_catalog_lookup(db)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        while imported < safe_target:
            if not await get_rate_limiter().acquire("IGDB"):
                break
            request_size = min(safe_page_size, safe_target - imported)
            response = await client.post(
                IGDB_GAMES_URL,
                headers=headers,
                content=build_full_catalog_query(after_id=after_id, page_size=request_size),
            )
            if response.status_code in (401, 403):
                raise RuntimeError(_IGDB_CREDENTIALS_REJECTED)
            response.raise_for_status()
            results = response.json()
            if not isinstance(results, list) or not results:
                state.completed = True
                state.last_success_at = datetime.now(UTC)
                state.updated_at = state.last_success_at
                db.commit()
                break

            state.completed = False
            for raw_game in results:
                if not isinstance(raw_game, dict):
                    continue
                raw_id = raw_game.get("id")
                if isinstance(raw_id, int):
                    after_id = max(after_id, raw_id)
                examined += 1
                if not str(raw_game.get("name") or "").strip():
                    skipped += 1
                    continue
                if _ingest_igdb_game(
                    db,
                    raw_game,
                    catalog_label="full",
                    default_platforms=None,
                    lookup=lookup,
                ):
                    imported += 1
                else:
                    skipped += 1

            now = datetime.now(UTC)
            state.cursor = {"after_id": after_id}
            state.last_success_at = now
            state.updated_at = now
            db.commit()
            if len(results) < request_size:
                state.completed = True
                state.updated_at = datetime.now(UTC)
                db.commit()
                break

    return {
        "imported": imported,
        "skipped": skipped,
        "examined": examined,
        "after_id": after_id,
        "completed": state.completed,
    }
