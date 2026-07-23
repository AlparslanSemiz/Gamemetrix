"""Per-source metadata refresh (Steam, RAWG, IGDB) and per-game orchestration.

Each `refresh_*` returns `(attempted, changed)`: whether the source was actually
queried (vs. skipped for budget) and whether it changed the row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...integrations.igdb_service import igdb_service
from ...integrations.rate_limiter import get_rate_limiter
from ...integrations.rawg import enrich_rawg_game_detail
from ...integrations.steam import extract_steam_app_id
from ...integrations.steam_service import steam_service
from ...models import ExternalId, Game
from .apply import apply_normalized_game
from .gaps import field_gaps, metadata_gap_score
from .persistence import has_external_id, store_source_snapshot, upsert_external_id
from .sanitize import is_missing_cover, steam_cover_should_update, titles_match_game

RefreshResult = tuple[bool, bool]

_STEAM_GAPS = {"cover", "website", "screenshots", "system_requirements", "developer", "publisher"}
_RAWG_GAPS = {
    "cover", "summary", "developer", "publisher", "genres",
    "platforms", "screenshots", "system_requirements", "dlcs", "similar_games",
}
_IGDB_GAPS = {"cover", "summary", "developer", "publisher", "genres", "platforms", "game_modes"}

_STEAM_CONFIDENCE = 0.96
_IGDB_TRUSTED_CONFIDENCE = 0.94
_IGDB_WEAK_CONFIDENCE = 0.7
_EARLIEST_MEANINGFUL_YEAR = 1970

_REFRESH_ORDER = ("Steam", "RAWG", "IGDB")


def source_needed(db: Session, game: Game, source: str) -> bool:
    gaps = field_gaps(game)
    if source == "Steam":
        return game.is_pc_applicable and (
            not has_external_id(db, game, "Steam") or bool(gaps & _STEAM_GAPS)
        )
    if source == "RAWG":
        return not has_external_id(db, game, "RAWG") or bool(gaps & _RAWG_GAPS)
    if source == "IGDB":
        return not has_external_id(db, game, "IGDB") or bool(gaps & _IGDB_GAPS)
    return False


def _release_year(game: Game) -> int | None:
    return game.release_year if game.release_year > _EARLIEST_MEANINGFUL_YEAR else None


async def refresh_steam_metadata(db: Session, game: Game, skipped: set[str]) -> RefreshResult:
    app_id = _resolve_steam_app_id(db, game)
    trusted_app_id = app_id is not None
    required_requests = 1 if trusted_app_id else 2
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
    if not trusted_app_id and not titles_match_game(game, result):
        return True, False

    prefer_cover = is_missing_cover(game.cover_url) or steam_cover_should_update(
        game.cover_url, app_id, result.cover_url
    )
    changed = apply_normalized_game(game, result, trusted=True, prefer_cover=prefer_cover)
    if game.steam_app_id != app_id:
        # Persist the resolved id so later refreshes skip the title-search round-trip.
        game.steam_app_id = app_id
        changed = True
    upsert_external_id(
        db, game.id, "Steam", str(app_id),
        url=steam_service.store_url(app_id), confidence=_STEAM_CONFIDENCE,
    )
    store_source_snapshot(db, game, result, "metadata-backfill/appdetails")
    return True, changed


def _resolve_steam_app_id(db: Session, game: Game) -> int | None:
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


async def refresh_igdb_metadata(db: Session, game: Game, skipped: set[str]) -> RefreshResult:
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
        result = await igdb_service.search_game(game.title, release_year=_release_year(game))
    if not result:
        return True, False
    if not trusted and not titles_match_game(game, result):
        return True, False

    changed = apply_normalized_game(game, result, trusted=trusted)
    upsert_external_id(
        db, game.id, "IGDB", result.external_id,
        slug=result.external_slug, url=result.external_url,
        confidence=_IGDB_TRUSTED_CONFIDENCE if trusted or titles_match_game(game, result) else _IGDB_WEAK_CONFIDENCE,
    )
    store_source_snapshot(db, game, result, "metadata-backfill/search")
    return True, changed


async def refresh_rawg_metadata(db: Session, game: Game, skipped: set[str]) -> RefreshResult:
    if not get_settings().rawg_configured():
        return False, False
    if get_rate_limiter().remaining("RAWG") <= 0:
        skipped.add("RAWG")
        return False, False
    before = metadata_gap_score(game)
    changed = await enrich_rawg_game_detail(db, game)
    after = metadata_gap_score(game)
    return True, changed or after < before


_REFRESHERS = {
    "Steam": refresh_steam_metadata,
    "RAWG": refresh_rawg_metadata,
    "IGDB": refresh_igdb_metadata,
}


async def refresh_game_metadata(db: Session, game: Game) -> dict[str, object]:
    attempted: list[str] = []
    changed_sources: list[str] = []
    budget_skipped: set[str] = set()
    changed = False

    for source in _REFRESH_ORDER:
        if not source_needed(db, game, source):
            continue
        source_attempted, source_changed = await _REFRESHERS[source](db, game, budget_skipped)
        if not source_attempted:
            continue
        attempted.append(source)
        if source_changed:
            changed = True
            changed_sources.append(source)

    if attempted:
        game.metadata_refreshed_at = datetime.now(UTC)
        from ..seo import refresh_game_seo_state
        refresh_game_seo_state(game, content_updated=changed)
        db.add(game)
        db.commit()
        db.refresh(game)

    return {
        "attempted": attempted,
        "changed": changed,
        "changed_sources": changed_sources,
        "budget_skipped": sorted(budget_skipped),
        "remaining_gaps": sorted(field_gaps(game)),
    }
