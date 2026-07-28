"""Fill missing PC requirements from Steam for games with a trusted App ID."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, exists, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.steam_service import steam_service
from ..integrations.title_matching import normalize_title, titles_match
from ..models import Game, SourceSnapshot
from .metadata_backfill.sanitize import system_requirements_need_repair

log = logging.getLogger(__name__)

_SNAPSHOT_ENDPOINT = "metadata-backfill/steam-system-requirements-v1"
_RETRY_AFTER = timedelta(days=90)
_PC_PLATFORM_NAMES = ("PC", "Steam", "Windows", "Microsoft Windows", "PC Windows")
_MAX_REQUIREMENT_ROWS = 12
_REMAKE_SUFFIXES = (" remake", " remastered")


def _identity_matches(
    game_title: str,
    provider_title: str | None,
    *,
    game_year: int | None = None,
    provider_year: int | None = None,
) -> bool:
    if titles_match(game_title, provider_title):
        return True
    if (
        not game_year
        or not provider_year
        or abs(game_year - provider_year) > 2
    ):
        return False
    expected = normalize_title(game_title)
    candidate = normalize_title(provider_title)
    for suffix in _REMAKE_SUFFIXES:
        if expected.endswith(suffix):
            expected = expected.removesuffix(suffix).strip()
        if candidate.endswith(suffix):
            candidate = candidate.removesuffix(suffix).strip()
    return bool(expected and expected == candidate)


def _candidates(db: Session, limit: int) -> list[tuple[int, int, str, int]]:
    retry_cutoff = datetime.now(UTC) - _RETRY_AFTER
    checked_recently = exists(
        select(SourceSnapshot.id).where(
            SourceSnapshot.source == "Steam",
            SourceSnapshot.endpoint == _SNAPSHOT_ENDPOINT,
            SourceSnapshot.external_id == cast(Game.steam_app_id, String),
            SourceSnapshot.fetched_at >= retry_cutoff,
        )
    )
    pc_platform = or_(*(
        Game.platforms.cast(JSONB).contains([platform])
        for platform in _PC_PLATFORM_NAMES
    ))
    rows = db.execute(
        select(
            Game.id,
            Game.steam_app_id,
            Game.title,
            Game.release_year,
            Game.system_requirements,
        )
        .where(
            Game.content_type == "game",
            Game.steam_app_id.is_not(None),
            pc_platform,
            ~checked_recently,
        )
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc())
        .execution_options(yield_per=500)
    )
    candidates: list[tuple[int, int, str, int]] = []
    for game_id, app_id, title, release_year, requirements in rows:
        if (
            app_id is not None
            and int(app_id) > 0
            and system_requirements_need_repair(requirements)
        ):
            candidates.append((
                int(game_id),
                int(app_id),
                str(title),
                int(release_year),
            ))
            if len(candidates) >= max(0, limit):
                break
    return candidates


def _requirements_from_raw(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    requirements = [
        {
            "platform": str(row.get("platform") or "").strip(),
            "minimum": str(row.get("minimum") or "").strip(),
            "recommended": str(row.get("recommended") or "").strip(),
        }
        for row in raw[:_MAX_REQUIREMENT_ROWS]
        if isinstance(row, dict)
    ]
    return requirements if not system_requirements_need_repair(requirements) else []


def _store_result(
    game_id: int,
    app_id: int,
    requirements: list[dict],
    *,
    provider_title: str | None,
    identity_matched: bool,
) -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        game = db.get(Game, game_id)
        filled = False
        if (
            game is not None
            and system_requirements_need_repair(game.system_requirements)
            and requirements
        ):
            game.system_requirements = requirements
            db.add(game)
            filled = True
        db.add(
            SourceSnapshot(
                source="Steam",
                endpoint=_SNAPSHOT_ENDPOINT,
                query=None,
                external_id=str(app_id),
                status_code=200,
                raw_payload={
                    "system_requirements_found": bool(requirements),
                    "provider_title": provider_title,
                    "identity_matched": identity_matched,
                    "platforms": [
                        row["platform"] for row in requirements if row["platform"]
                    ],
                },
                fetched_at=now,
                created_at=now,
            )
        )
        db.commit()
    return filled


async def steam_system_requirements_backfill_batch(
    limit: int = 1_000,
    *,
    inter_game_delay: float = 0.35,
) -> dict[str, int]:
    with SessionLocal() as db:
        candidates = _candidates(db, limit)

    considered = filled = unavailable = failed = 0
    for game_id, app_id, title, release_year in candidates:
        if get_rate_limiter().remaining("Steam") <= 0:
            break
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        try:
            result = await steam_service.get_app_details(app_id)
        except Exception:
            log.debug(
                "Steam system-requirements lookup failed for app_id=%d",
                app_id,
                exc_info=True,
            )
            failed += 1
            continue
        considered += 1
        if result is None:
            failed += 1
            continue
        identity_matched = _identity_matches(
            title,
            result.name,
            game_year=release_year,
            provider_year=result.release_date.year if result.release_date else None,
        )
        requirements = (
            _requirements_from_raw(result.raw.get("system_requirements"))
            if identity_matched
            else []
        )
        if _store_result(
            game_id,
            app_id,
            requirements,
            provider_title=result.name,
            identity_matched=identity_matched,
        ):
            filled += 1
        else:
            unavailable += 1
    return {
        "considered": considered,
        "filled": filled,
        "unavailable": unavailable,
        "failed": failed,
    }
