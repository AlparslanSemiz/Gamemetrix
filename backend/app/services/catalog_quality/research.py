"""Fetch normalized metadata from identity-checked catalog providers."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...integrations.igdb_service import igdb_service
from ...integrations.gamebrain_service import gamebrain_service
from ...integrations.rawg_service import rawg_service
from ...integrations.steam_service import steam_service
from ...integrations.title_matching import titles_match
from ...integrations.wikidata_service import wikidata_service
from ...models import ExternalId, Game
from .remediation import ResearchedGame

log = logging.getLogger(__name__)

_TRUSTED_ID_CONFIDENCE = 0.9
_EARLIEST_MEANINGFUL_YEAR = 1970


async def research_game(
    db: Session,
    game: Game,
    fields: set[str],
) -> list[ResearchedGame]:
    external_ids = {
        row.source: row
        for row in db.scalars(
            select(ExternalId).where(ExternalId.game_id == game.id)
        ).all()
    }
    allow_search = "title" not in fields
    results = await asyncio.gather(
        _research_steam(game, external_ids.get("Steam"), allow_search),
        _research_igdb(game, external_ids.get("IGDB"), allow_search),
        _research_wikidata(
            game,
            external_ids.get("Steam"),
            external_ids.get("IGDB"),
        ),
        _research_gamebrain(game, external_ids.get("GameBrain"), allow_search),
        _research_rawg(game, external_ids.get("RAWG"), allow_search),
        return_exceptions=True,
    )
    researched: list[ResearchedGame] = []
    for result in results:
        if isinstance(result, ResearchedGame):
            researched.append(result)
        elif isinstance(result, BaseException):
            log.debug(
                "Catalog remediation provider research failed (%s)",
                type(result).__name__,
            )
    return researched


async def _research_steam(
    game: Game,
    external: ExternalId | None,
    allow_search: bool,
) -> ResearchedGame | None:
    app_id = game.steam_app_id
    trusted = app_id is not None
    if app_id is None and _trusted_numeric_id(external):
        app_id = int(external.external_id)
        trusted = True
    if app_id is None and allow_search:
        app_id = await steam_service.lookup_app_id("", game.title)
    if app_id is None:
        return None
    record = await steam_service.get_app_details(app_id)
    if trusted and allow_search and record and not _search_identity_matches(
        game, record.name, record.release_date
    ):
        searched_id = await steam_service.lookup_app_id("", game.title)
        record = await steam_service.get_app_details(searched_id) if searched_id else None
        trusted = False
    if record is None or (not trusted and not _search_identity_matches(game, record.name, record.release_date)):
        return None
    return ResearchedGame(record=record, trusted_identity=trusted)


async def _research_igdb(
    game: Game,
    external: ExternalId | None,
    allow_search: bool,
) -> ResearchedGame | None:
    if not igdb_service.is_configured():
        return None
    trusted = _trusted_numeric_id(external)
    if trusted:
        record = await igdb_service.get_by_igdb_id(int(external.external_id))
    elif allow_search:
        record = await igdb_service.search_game(game.title, release_year=_release_year(game))
    else:
        record = None
    if trusted and allow_search and record and not _search_identity_matches(
        game, record.name, record.release_date
    ):
        record = await igdb_service.search_game(game.title, release_year=_release_year(game))
        trusted = False
    if record is None or (not trusted and not _search_identity_matches(game, record.name, record.release_date)):
        return None
    return ResearchedGame(record=record, trusted_identity=trusted)


async def _research_rawg(
    game: Game,
    external: ExternalId | None,
    allow_search: bool,
) -> ResearchedGame | None:
    if not rawg_service.is_configured():
        return None
    trusted = _trusted_numeric_id(external)
    if trusted:
        record = await rawg_service.get_by_rawg_id(int(external.external_id))
    elif allow_search:
        search = await rawg_service.search_game(game.title, release_year=_release_year(game))
        record = (
            await rawg_service.get_by_rawg_id(int(search.external_id))
            if search and search.external_id.isdigit()
            else search
        )
    else:
        record = None
    if trusted and allow_search and record and not _search_identity_matches(
        game, record.name, record.release_date
    ):
        search = await rawg_service.search_game(game.title, release_year=_release_year(game))
        record = (
            await rawg_service.get_by_rawg_id(int(search.external_id))
            if search and search.external_id.isdigit()
            else search
        )
        trusted = False
    if record is None or (not trusted and not _search_identity_matches(game, record.name, record.release_date)):
        return None
    return ResearchedGame(record=record, trusted_identity=trusted)


async def _research_wikidata(
    game: Game,
    steam_external: ExternalId | None,
    igdb_external: ExternalId | None,
) -> ResearchedGame | None:
    steam_app_id = game.steam_app_id
    if steam_app_id is None and _trusted_numeric_id(steam_external):
        steam_app_id = int(steam_external.external_id)
    igdb_slug = (
        igdb_external.external_slug
        if igdb_external
        and igdb_external.is_primary
        and igdb_external.confidence >= _TRUSTED_ID_CONFIDENCE
        else None
    )
    if not steam_app_id and not igdb_slug:
        return None
    record = await wikidata_service.lookup_exact(
        steam_app_id=steam_app_id,
        igdb_slug=igdb_slug,
    )
    return (
        ResearchedGame(record=record, trusted_identity=True)
        if record is not None
        else None
    )


async def _research_gamebrain(
    game: Game,
    external: ExternalId | None,
    allow_search: bool,
) -> ResearchedGame | None:
    if not gamebrain_service.is_configured():
        return None
    trusted = _trusted_numeric_id(external)
    if trusted:
        record = await gamebrain_service.get_detail(external.external_id)
    elif allow_search:
        record = await gamebrain_service.search_game(
            game.title,
            release_year=_release_year(game),
        )
    else:
        record = None
    if record is None or (
        not trusted
        and not _search_identity_matches(game, record.name, record.release_date)
    ):
        return None
    return ResearchedGame(record=record, trusted_identity=trusted)


def _trusted_numeric_id(external: ExternalId | None) -> bool:
    return bool(
        external
        and external.is_primary
        and external.confidence >= _TRUSTED_ID_CONFIDENCE
        and external.external_id.isdigit()
    )


def _search_identity_matches(game: Game, candidate: str, released: date | None) -> bool:
    return titles_match(
        game.title,
        candidate,
        expected_year=_release_year(game),
        candidate_year=released.year if released else None,
    )


def _release_year(game: Game) -> int | None:
    return game.release_year if game.release_year > _EARLIEST_MEANINGFUL_YEAR else None
