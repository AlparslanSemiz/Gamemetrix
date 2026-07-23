"""Match a catalog game against every configured source and upsert ExternalId rows.

Admin-triggered: given a game, search each provider by title and record the
provider's identifier so later refreshes can skip the search step.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..integrations.igdb_service import igdb_service
from ..integrations.itad_service import itad_service
from ..integrations.opencritic_service import opencritic_service
from ..integrations.rawg_service import rawg_service
from ..integrations.steam_service import steam_service
from ..models import ExternalId, Game

_MATCH_CONFIDENCE = 0.9
_EARLIEST_MEANINGFUL_YEAR = 1970


async def match_external_ids(db: Session, game: Game) -> list[str]:
    """Search every source for the game and upsert matches. Returns matched sources."""
    now = datetime.now(UTC)
    matched: list[str] = []

    await asyncio.gather(
        _match_search_source(db, game, "IGDB", igdb_service, matched, now, include_url=True),
        _match_search_source(db, game, "RAWG", rawg_service, matched, now, include_url=False),
        _match_search_source(db, game, "OpenCritic", opencritic_service, matched, now, include_url=True),
        _match_itad(db, game, matched, now),
        _match_steam(db, game, matched, now),
        return_exceptions=True,
    )
    db.commit()
    return matched


def _release_year(game: Game) -> int | None:
    return game.release_year if game.release_year > _EARLIEST_MEANINGFUL_YEAR else None


async def _match_search_source(
    db: Session,
    game: Game,
    source: str,
    service,
    matched: list[str],
    now: datetime,
    *,
    include_url: bool,
) -> None:
    result = await service.search_game(game.title, release_year=_release_year(game))
    if not result:
        return
    _upsert_external_id(
        db,
        game.id,
        source,
        result.external_id,
        result.external_slug,
        result.external_url if include_url else None,
        now,
    )
    matched.append(source)


async def _match_itad(db: Session, game: Game, matched: list[str], now: datetime) -> None:
    itad_id = await itad_service.lookup_id(game.title)
    if itad_id:
        _upsert_external_id(db, game.id, "ITAD", itad_id, None, None, now)
        matched.append("ITAD")


async def _match_steam(db: Session, game: Game, matched: list[str], now: datetime) -> None:
    app_id = await steam_service.lookup_app_id(game.slug, game.title)
    if app_id:
        _upsert_external_id(
            db, game.id, "Steam", str(app_id), None, steam_service.store_url(app_id), now
        )
        matched.append("Steam")


def _upsert_external_id(
    db: Session,
    game_id: int,
    source: str,
    external_id: str,
    slug: str | None,
    url: str | None,
    now: datetime,
) -> None:
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
        existing.updated_at = now
    else:
        db.add(
            ExternalId(
                game_id=game_id,
                source=source,
                external_id=external_id,
                external_slug=slug,
                external_url=url,
                confidence=_MATCH_CONFIDENCE,
                is_primary=True,
                created_at=now,
                updated_at=now,
            )
        )
