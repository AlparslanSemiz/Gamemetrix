"""Rotate through IGDB-linked games and fill optional fields plus Steam IDs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.igdb_optional_metadata import get_igdb_optional_metadata
from ..integrations.igdb_playtime import MAX_IGDB_PLAYTIME_BATCH
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.steam_service import steam_service
from ..models import ExternalId, Game, SourceSnapshot
from .metadata_backfill.persistence import upsert_external_id
from .metadata_backfill.sanitize import website_needs_repair

log = logging.getLogger(__name__)

_SNAPSHOT_ENDPOINT = "metadata-backfill/igdb-optional-bulk-v2"
_RETRY_AFTER = timedelta(days=30)
_STEAM_ID_CONFIDENCE = 0.98
_PC_PLATFORM_NAMES = ("PC", "Steam", "Windows", "Microsoft Windows", "PC Windows")
_PROVIDER_WEBSITE_PATTERNS = (
    "%://igdb.com/%",
    "%://www.igdb.com/%",
    "%://wikidata.org/%",
    "%://www.wikidata.org/%",
    "%://rawg.io/%",
    "%://www.rawg.io/%",
    "%://gamebrain.co/%",
    "%://www.gamebrain.co/%",
)


def _candidates(db: Session, limit: int) -> list[tuple[int, int]]:
    retry_cutoff = datetime.now(UTC) - _RETRY_AFTER
    checked_recently = exists(
        select(SourceSnapshot.id).where(
            SourceSnapshot.source == "IGDB",
            SourceSnapshot.endpoint == _SNAPSHOT_ENDPOINT,
            SourceSnapshot.external_id == ExternalId.external_id,
            SourceSnapshot.fetched_at >= retry_cutoff,
        )
    )
    website_missing_or_profile = or_(
        Game.website_url.is_(None),
        Game.website_url == "",
        *(Game.website_url.ilike(pattern) for pattern in _PROVIDER_WEBSITE_PATTERNS),
    )
    pc_platform = or_(*(
        Game.platforms.cast(JSONB).contains([platform])
        for platform in _PC_PLATFORM_NAMES
    ))
    missing_steam_identity = and_(
        pc_platform,
        Game.steam_app_id.is_(None),
    )
    rows = db.execute(
        select(Game.id, ExternalId.external_id)
        .join(ExternalId, and_(ExternalId.game_id == Game.id, ExternalId.source == "IGDB"))
        .where(
            Game.content_type == "game",
            or_(
                website_missing_or_profile,
                func.jsonb_array_length(Game.game_modes) == 0,
                missing_steam_identity,
            ),
            ~checked_recently,
        )
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc())
        .limit(limit)
    ).all()
    candidates: list[tuple[int, int]] = []
    for game_id, external_id in rows:
        if external_id and str(external_id).isdigit():
            candidates.append((int(game_id), int(external_id)))
    return candidates


def _chunks(
    candidates: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    return [
        candidates[index:index + MAX_IGDB_PLAYTIME_BATCH]
        for index in range(0, len(candidates), MAX_IGDB_PLAYTIME_BATCH)
    ]


def _store_batch(
    candidates: list[tuple[int, int]],
    metadata: dict[int, dict[str, object]],
) -> tuple[int, int, int, int]:
    now = datetime.now(UTC)
    website_filled = modes_filled = steam_ids_filled = skipped = 0
    with SessionLocal() as db:
        for game_id, igdb_id in candidates:
            values = metadata.get(igdb_id) or {}
            game = db.get(Game, game_id)
            changed = False
            website = values.get("website")
            modes = values.get("game_modes")
            steam_app_id = values.get("steam_app_id")
            if (
                game is not None
                and isinstance(website, str)
                and website_needs_repair(game.website_url)
            ):
                game.website_url = website
                website_filled += 1
                changed = True
            if game is not None and isinstance(modes, list) and modes and not game.game_modes:
                game.game_modes = modes
                modes_filled += 1
                changed = True
            if (
                game is not None
                and isinstance(steam_app_id, int)
                and steam_app_id > 0
                and game.steam_app_id != steam_app_id
            ):
                game.steam_app_id = steam_app_id
                upsert_external_id(
                    db,
                    game.id,
                    "Steam",
                    str(steam_app_id),
                    url=steam_service.store_url(steam_app_id),
                    confidence=_STEAM_ID_CONFIDENCE,
                )
                steam_ids_filled += 1
                changed = True
            if game is not None and changed:
                db.add(game)
            if not changed:
                skipped += 1
            db.add(
                SourceSnapshot(
                    source="IGDB",
                    endpoint=_SNAPSHOT_ENDPOINT,
                    query=None,
                    external_id=str(igdb_id),
                    status_code=200,
                    raw_payload={
                        "website_found": isinstance(website, str),
                        "game_modes_found": bool(modes),
                        "steam_app_id_found": isinstance(steam_app_id, int),
                    },
                    fetched_at=now,
                    created_at=now,
                )
            )
        db.commit()
    return website_filled, modes_filled, steam_ids_filled, skipped


async def igdb_optional_metadata_backfill_batch(
    limit: int = 5_000,
    *,
    inter_batch_delay: float = 0.35,
) -> dict[str, int]:
    with SessionLocal() as db:
        candidates = _candidates(db, limit)

    considered = website_filled = modes_filled = steam_ids_filled = skipped = failed = 0
    for batch in _chunks(candidates):
        if get_rate_limiter().remaining("IGDB") <= 0:
            break
        if not await get_rate_limiter().acquire("IGDB"):
            break
        if inter_batch_delay > 0:
            await asyncio.sleep(inter_batch_delay)
        try:
            metadata = await get_igdb_optional_metadata(
                [igdb_id for _, igdb_id in batch]
            )
        except Exception:
            log.debug("IGDB optional metadata batch failed", exc_info=True)
            failed += len(batch)
            continue
        considered += len(batch)
        if metadata is None:
            failed += len(batch)
            continue
        batch_websites, batch_modes, batch_steam_ids, batch_skipped = _store_batch(
            batch,
            metadata,
        )
        website_filled += batch_websites
        modes_filled += batch_modes
        steam_ids_filled += batch_steam_ids
        skipped += batch_skipped
    return {
        "considered": considered,
        "website_filled": website_filled,
        "modes_filled": modes_filled,
        "steam_ids_filled": steam_ids_filled,
        "skipped": skipped,
        "failed": failed,
    }
