"""
Rate-limited metadata backfill for existing games.

This complements score refreshes: it fills cover art, descriptions,
developer/publisher, platform/genre gaps, screenshots, system requirements,
website URLs, and external IDs in small periodic batches.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..heavy_jobs import HEAVY_JOB_LOCK
from ..integrations.igdb_service import igdb_service
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.rawg import enrich_rawg_game_detail
from ..integrations.steam import extract_steam_app_id
from ..integrations.steam_service import steam_service
from ..integrations.title_matching import titles_match
from ..integrations.types import NormalizedGame
from ..models import ExternalId, Game, SourceSnapshot
from .metadata import clean_game_summary, summary_needs_enrichment


log = logging.getLogger(__name__)

METADATA_BACKFILL_LOCK = HEAVY_JOB_LOCK

_DEFAULT_STALE_AFTER = timedelta(days=21)
_DEFAULT_RETRY_AFTER = timedelta(hours=18)
_COVER_RETRY_AFTER = timedelta(hours=6)
_MAX_SCREENSHOTS = 16

_GENERIC_GENRES = {(), ("Uncategorized",), ("Steam",), ("Deal", "PC")}
_GENERIC_PLATFORMS = {(), ("Unknown",)}
_BAD_SYSTEM_REQUIREMENT_MARKERS = (
    "windows xp",
    "1.2ghz",
    "256mb",
    "250 mb",
)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _titles_match(game: Game, candidate: NormalizedGame) -> bool:
    return titles_match(
        game.title,
        candidate.name,
        expected_year=game.release_year if game.release_year > 1970 else None,
        candidate_year=candidate.release_date.year if candidate.release_date else None,
    )


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if not url or len(url) > 500 or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    parsed = urlsplit(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return url


def _is_missing_cover(value: str | None) -> bool:
    if not value or not value.strip():
        return True
    lowered = value.lower()
    return (
        lowered.startswith("data:image")
        or "placeholder" in lowered
        or lowered in {"none", "null"}
    )


def _steam_cover_should_update(current: str | None, app_id: int, fresh: str | None) -> bool:
    if not fresh or not current:
        return False
    if current == fresh:
        return False
    return f"/steam/apps/{app_id}/" in current and "store_item_assets" not in current


def _system_requirements_need_repair(requirements: list[dict] | None) -> bool:
    if not requirements:
        return True
    pc_req = next(
        (req for req in requirements if str(req.get("platform", "")).lower() in {"pc", "windows"}),
        requirements[0],
    )
    text = " ".join(str(pc_req.get(key) or "") for key in ("minimum", "recommended")).lower()
    if not text.strip():
        return True
    return any(marker in text for marker in _BAD_SYSTEM_REQUIREMENT_MARKERS)


def _tupled(values: list[str] | None) -> tuple[str, ...]:
    return tuple(values or [])


def _has_external_id(db: Session, game: Game, source: str) -> bool:
    if not game.id:
        return False
    return db.scalar(
        select(ExternalId.id)
        .where(ExternalId.game_id == game.id, ExternalId.source == source)
        .limit(1)
    ) is not None


def upsert_external_id(
    db: Session,
    game_id: int,
    source: str,
    external_id: str,
    *,
    slug: str | None = None,
    url: str | None = None,
    confidence: float = 0.9,
) -> None:
    now = datetime.now(UTC)
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game_id,
            ExternalId.source == source,
        )
    )
    if existing:
        existing.external_id = external_id
        existing.external_slug = slug
        existing.external_url = url
        existing.confidence = max(existing.confidence, confidence)
        existing.updated_at = now
        return

    db.add(ExternalId(
        game_id=game_id,
        source=source,
        external_id=external_id,
        external_slug=slug,
        external_url=url,
        confidence=confidence,
        is_primary=True,
        created_at=now,
        updated_at=now,
    ))


def _store_source_snapshot(db: Session, game: Game, result: NormalizedGame, endpoint: str) -> None:
    now = datetime.now(UTC)
    db.add(SourceSnapshot(
        source=result.source,
        endpoint=endpoint,
        query=game.title,
        external_id=result.external_id,
        status_code=None,
        raw_payload=result.raw,
        fetched_at=now,
        created_at=now,
    ))


def _field_gaps(game: Game) -> set[str]:
    gaps: set[str] = set()
    if _is_missing_cover(game.cover_url):
        gaps.add("cover")
    if summary_needs_enrichment(game):
        gaps.add("summary")
    if not game.developer:
        gaps.add("developer")
    if not game.publisher:
        gaps.add("publisher")
    if not game.game_modes:
        gaps.add("game_modes")
    if _tupled(game.genres) in _GENERIC_GENRES:
        gaps.add("genres")
    if _tupled(game.platforms) in _GENERIC_PLATFORMS:
        gaps.add("platforms")
    if not game.website_url:
        gaps.add("website")
    if not game.screenshots:
        gaps.add("screenshots")
    if game.is_pc_applicable and _system_requirements_need_repair(game.system_requirements):
        gaps.add("system_requirements")
    if not game.dlcs:
        gaps.add("dlcs")
    if not game.similar_games:
        gaps.add("similar_games")
    return gaps


def metadata_gap_score(game: Game) -> int:
    weights = {
        "cover": 100,
        "summary": 28,
        "developer": 16,
        "publisher": 16,
        "game_modes": 14,
        "genres": 12,
        "platforms": 12,
        "screenshots": 10,
        "system_requirements": 8,
        "website": 6,
        "dlcs": 3,
        "similar_games": 3,
    }
    return sum(weights.get(gap, 1) for gap in _field_gaps(game))


def game_needs_metadata_backfill(
    game: Game,
    now: datetime | None = None,
    *,
    stale_after: timedelta = _DEFAULT_STALE_AFTER,
    retry_after: timedelta = _DEFAULT_RETRY_AFTER,
) -> bool:
    gaps = _field_gaps(game)
    if not gaps:
        return False

    now = now or datetime.now(UTC)
    refreshed_at = _as_aware(game.metadata_refreshed_at)
    if refreshed_at is None:
        return True

    effective_retry = _COVER_RETRY_AFTER if "cover" in gaps else retry_after
    return now - refreshed_at >= min(stale_after, effective_retry)


def metadata_backfill_candidates(db: Session, limit: int | None = None) -> list[Game]:
    now = datetime.now(UTC)
    pool_limit = max((limit or 50) * 10, 200)
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .order_by(
                desc(Game.metadata_refreshed_at.is_(None)),
                asc(Game.metadata_refreshed_at),
                desc(Game.rank_score),
                desc(Game.metrix_score),
            )
            .limit(pool_limit)
        ).all()
    )
    due = [game for game in games if game_needs_metadata_backfill(game, now)]
    due.sort(key=lambda game: (-metadata_gap_score(game), _metadata_ts(game), -game.rank_score))
    return due[:limit] if limit is not None else due


def _metadata_ts(game: Game) -> float:
    refreshed_at = _as_aware(game.metadata_refreshed_at)
    return refreshed_at.timestamp() if refreshed_at else 0.0


def _source_needed(db: Session, game: Game, source: str) -> bool:
    gaps = _field_gaps(game)
    if source == "Steam":
        return game.is_pc_applicable and (
            not _has_external_id(db, game, "Steam")
            or bool(gaps & {"cover", "website", "screenshots", "system_requirements", "developer", "publisher"})
        )
    if source == "RAWG":
        return (
            not _has_external_id(db, game, "RAWG")
            or bool(gaps & {"cover", "summary", "developer", "publisher", "genres", "platforms", "screenshots", "system_requirements", "dlcs", "similar_games"})
        )
    if source == "IGDB":
        return (
            not _has_external_id(db, game, "IGDB")
            or bool(gaps & {"cover", "summary", "developer", "publisher", "genres", "platforms", "game_modes"})
        )
    return False


def _merge_unique(current: list[str] | None, incoming: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in [*(current or []), *incoming]:
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
        if len(merged) >= limit:
            break
    return merged


def _apply_normalized_game(
    game: Game,
    result: NormalizedGame,
    *,
    trusted: bool = False,
    prefer_cover: bool = False,
) -> bool:
    if not trusted and not _titles_match(game, result):
        return False

    changed = False
    cover_url = _safe_url(result.cover_url)
    if cover_url and (prefer_cover or _is_missing_cover(game.cover_url)):
        if game.cover_url != cover_url:
            game.cover_url = cover_url
            game.image_url = cover_url
            changed = True

    summary = clean_game_summary(result.summary, game.title)
    if summary and (summary_needs_enrichment(game) or len(summary) > len(game.summary)):
        game.summary = summary
        changed = True

    if result.release_date and result.release_date.year > 1970:
        if game.release_year == 1970 or game.release_date.year == 1970:
            game.release_date = result.release_date
            game.release_year = result.release_date.year
            changed = True
        if game.official_release_date is None:
            game.official_release_date = result.release_date
            changed = True

    if result.developer and not game.developer:
        game.developer = result.developer[:200]
        changed = True
    if result.publisher and not game.publisher:
        game.publisher = result.publisher[:200]
        changed = True
    if result.franchise and game.franchise != result.franchise[:200]:
        game.franchise = result.franchise[:200]
        changed = True

    if result.genres and _tupled(game.genres) in _GENERIC_GENRES:
        game.genres = result.genres[:6]
        changed = True
    if result.game_modes and not game.game_modes:
        game.game_modes = result.game_modes
        changed = True
    if result.platforms and _tupled(game.platforms) in _GENERIC_PLATFORMS:
        game.platforms = result.platforms[:12]
        changed = True

    raw_website = result.raw.get("website")
    website = _safe_url(
        result.external_url if result.source != "Steam"
        else raw_website if isinstance(raw_website, str)
        else None
    )
    if website and not game.website_url:
        game.website_url = website
        changed = True

    raw_screenshots = result.raw.get("screenshots", [])
    if not isinstance(raw_screenshots, list):
        raw_screenshots = []
    screenshots = [
        safe
        for url in raw_screenshots[:_MAX_SCREENSHOTS]
        if isinstance(url, str) and (safe := _safe_url(url)) is not None
    ]
    if screenshots and not game.screenshots:
        game.screenshots = _merge_unique(game.screenshots, screenshots, _MAX_SCREENSHOTS)
        changed = True

    raw_requirements = result.raw.get("system_requirements", [])
    if not isinstance(raw_requirements, list):
        raw_requirements = []
    requirements = [
        row for row in raw_requirements[:12]
        if isinstance(row, dict)
    ]
    if requirements and _system_requirements_need_repair(game.system_requirements):
        game.system_requirements = requirements
        changed = True

    return changed


async def _refresh_steam_metadata(db: Session, game: Game, skipped: set[str]) -> tuple[bool, bool]:
    app_id = _steam_app_id(db, game)
    trusted_app_id = app_id is not None
    required_requests = 1 if app_id is not None else 2
    if get_rate_limiter().remaining("Steam") < required_requests:
        skipped.add("Steam")
        return False, False
    if app_id is None:
        app_id = await steam_service.lookup_app_id(game.slug, game.title)
    if app_id is None:
        return True, False

    result = await steam_service.get_app_details(app_id)
    if not result:
        return True, False
    if not trusted_app_id and not _titles_match(game, result):
        return True, False

    prefer_cover = _is_missing_cover(game.cover_url) or _steam_cover_should_update(
        game.cover_url,
        app_id,
        result.cover_url,
    )
    changed = _apply_normalized_game(game, result, trusted=True, prefer_cover=prefer_cover)
    if game.steam_app_id != app_id:
        # Persist the resolved id so later refreshes skip the title-search round-trip.
        game.steam_app_id = app_id
        changed = True
    upsert_external_id(
        db,
        game.id,
        "Steam",
        str(app_id),
        url=steam_service.store_url(app_id),
        confidence=0.96,
    )
    _store_source_snapshot(db, game, result, "metadata-backfill/appdetails")
    return True, changed


def _steam_app_id(db: Session, game: Game) -> int | None:
    if game.steam_app_id:
        return game.steam_app_id
    external = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == "Steam",
        )
    )
    if external and external.external_id.isdigit():
        return int(external.external_id)
    return extract_steam_app_id(game.slug, game.cover_url, game.image_url)


async def _refresh_igdb_metadata(db: Session, game: Game, skipped: set[str]) -> tuple[bool, bool]:
    if not igdb_service.is_configured():
        return False, False
    if get_rate_limiter().remaining("IGDB") <= 0:
        skipped.add("IGDB")
        return False, False

    external = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == "IGDB",
        )
    )
    result = None
    trusted = False
    if external and external.external_id.isdigit():
        result = await igdb_service.get_by_igdb_id(int(external.external_id))
        trusted = result is not None
    if result is None:
        result = await igdb_service.search_game(
            game.title,
            release_year=game.release_year if game.release_year > 1970 else None,
        )
    if not result:
        return True, False
    if not trusted and not _titles_match(game, result):
        return True, False

    changed = _apply_normalized_game(game, result, trusted=trusted)
    upsert_external_id(
        db,
        game.id,
        "IGDB",
        result.external_id,
        slug=result.external_slug,
        url=result.external_url,
        confidence=0.94 if trusted or _titles_match(game, result) else 0.7,
    )
    _store_source_snapshot(db, game, result, "metadata-backfill/search")
    return True, changed


async def _refresh_rawg_metadata(db: Session, game: Game, skipped: set[str]) -> tuple[bool, bool]:
    if not get_settings().rawg_configured():
        return False, False
    if get_rate_limiter().remaining("RAWG") <= 0:
        skipped.add("RAWG")
        return False, False
    before = metadata_gap_score(game)
    changed = await enrich_rawg_game_detail(db, game)
    after = metadata_gap_score(game)
    return True, changed or after < before


async def refresh_game_metadata(db: Session, game: Game) -> dict[str, object]:
    attempted: list[str] = []
    changed_sources: list[str] = []
    budget_skipped: set[str] = set()
    changed = False

    for source, refresh in (
        ("Steam", _refresh_steam_metadata),
        ("RAWG", _refresh_rawg_metadata),
        ("IGDB", _refresh_igdb_metadata),
    ):
        if not _source_needed(db, game, source):
            continue
        source_attempted, source_changed = await refresh(db, game, budget_skipped)
        if not source_attempted:
            continue
        attempted.append(source)
        if source_changed:
            changed = True
            changed_sources.append(source)

    if attempted:
        game.metadata_refreshed_at = datetime.now(UTC)
        from .seo import refresh_game_seo_state
        refresh_game_seo_state(game, content_updated=changed)
        db.add(game)
        db.commit()
        db.refresh(game)

    return {
        "attempted": attempted,
        "changed": changed,
        "changed_sources": changed_sources,
        "budget_skipped": sorted(budget_skipped),
        "remaining_gaps": sorted(_field_gaps(game)),
    }


async def metadata_backfill_batch(
    limit: int = 24,
    *,
    inter_game_delay: float = 0.5,
    use_lock: bool = True,
    refresh_seo: bool = True,
) -> dict[str, object]:
    if not use_lock:
        return await _metadata_backfill_batch_unlocked(
            limit=limit,
            inter_game_delay=inter_game_delay,
            refresh_seo=refresh_seo,
        )

    if METADATA_BACKFILL_LOCK.locked():
        return {
            "status": "already_running",
            "considered": 0,
            "enriched": 0,
            "changed": 0,
            "skipped": 0,
            "budget_skipped": {},
            "failed": 0,
        }

    async with METADATA_BACKFILL_LOCK:
        return await _metadata_backfill_batch_unlocked(
            limit=limit,
            inter_game_delay=inter_game_delay,
            refresh_seo=refresh_seo,
        )


async def _metadata_backfill_batch_unlocked(
    *,
    limit: int,
    inter_game_delay: float,
    refresh_seo: bool,
) -> dict[str, object]:
    with SessionLocal() as db:
        candidates = [game.id for game in metadata_backfill_candidates(db, limit=limit)]

    enriched = 0
    changed = 0
    skipped = 0
    failed = 0
    budget_skipped: dict[str, int] = {}

    for game_id in candidates:
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None or not game_needs_metadata_backfill(game):
                skipped += 1
                continue
            try:
                result = await refresh_game_metadata(db, game)
            except Exception:
                failed += 1
                log.debug("metadata_backfill_batch failed for game_id=%d", game_id, exc_info=True)
                continue
            if not result["attempted"]:
                skipped += 1
            else:
                enriched += 1
            if result["changed"]:
                changed += 1
            for source in result["budget_skipped"]:
                budget_skipped[source] = budget_skipped.get(source, 0) + 1

    if changed and refresh_seo:
        with SessionLocal() as db:
            from .seo import refresh_catalog_seo_states
            refresh_catalog_seo_states(db)
            db.commit()

    log.info(
        "metadata_backfill_batch done: %d enriched, %d changed, %d skipped, %d failed",
        enriched,
        changed,
        skipped,
        failed,
    )
    return {
        "status": "ok",
        "considered": len(candidates),
        "enriched": enriched,
        "changed": changed,
        "skipped": skipped,
        "budget_skipped": budget_skipped,
        "failed": failed,
    }
