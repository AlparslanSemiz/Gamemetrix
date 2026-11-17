"""Normalized/fuzzy/alias title search, playtime filter, release-date repair, content type."""

import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from app.content_type import content_type_from_steam_type, infer_content_type
from app.integrations.steam.client import AppdetailsOutcome
from app.models import Game, GameSearchAlias
from app.search_text import normalize_search_text
from app.services.game_query import CatalogFilters, apply_advanced_filters, build_catalog_query
from app.services.release_date_repair import classify, repair_release_dates

from .pg_support import make_game, pg_session, requires_postgres  # noqa: F401


def test_search_text_normalization() -> None:
    assert normalize_search_text("Marvel's Spider-Man: Miles Morales") == "marvels spider man miles morales"
    assert normalize_search_text("Pokémon  Legends: Z-A") == "pokemon legends z a"
    assert normalize_search_text("  ") == ""
    assert normalize_search_text(None) == ""


def _search(db, q: str) -> set[str]:
    query = build_catalog_query("all", q, None, None, None, None, "all", "title", "asc")
    return {game.title for game in db.scalars(query).all()}


@requires_postgres
def test_search_ignores_accents_punctuation_and_apostrophes(pg_session) -> None:
    pg_session.add_all([
        make_game("Pokémon Legends: Arceus", "pokemon-legends-arceus"),
        make_game("Marvel's Spider-Man", "marvels-spider-man"),
        make_game("Half-Life 2", "half-life-2"),
        make_game("Hades", "hades"),
    ])
    pg_session.commit()
    assert _search(pg_session, "pokemon legends") == {"Pokémon Legends: Arceus"}
    assert _search(pg_session, "marvels spider man") == {"Marvel's Spider-Man"}
    assert _search(pg_session, "Marvel’s Spider‑Man") == {"Marvel's Spider-Man"}
    assert _search(pg_session, "half life 2") == {"Half-Life 2"}
    assert _search(pg_session, "hades") == {"Hades"}


@requires_postgres
def test_search_trigram_fallback_and_aliases(pg_session) -> None:
    gta = make_game("Grand Theft Auto V", "grand-theft-auto-v")
    pg_session.add_all([gta, make_game("Baldur's Gate 3", "baldurs-gate-3"), make_game("Hades", "hades")])
    pg_session.flush()
    pg_session.add(GameSearchAlias(alias="gta 5", game_id=gta.id))
    pg_session.commit()
    assert _search(pg_session, "gta 5") == {"Grand Theft Auto V"}
    assert _search(pg_session, "baldur gate 3") == {"Baldur's Gate 3"}  # typo/missing letter -> trigram
    assert _search(pg_session, "zzzzzz") == set()


@requires_postgres
def test_title_normalized_is_maintained_on_insert_and_update(pg_session) -> None:
    game = make_game("Tom Clancy's Rainbow Six", "rainbow-six")
    pg_session.add(game)
    pg_session.commit()
    assert game.title_normalized == "tom clancys rainbow six"
    game.title = "Rainbow Six: Siege"
    pg_session.commit()
    assert game.title_normalized == "rainbow six siege"


@requires_postgres
def test_playtime_filter_prefers_hltb_and_skips_endless(pg_session) -> None:
    pg_session.add_all([
        make_game("RDR2", "rdr2", playtime_minutes=6000, hltb_main_story_minutes=3060),
        make_game("Only Provider", "only-provider", playtime_minutes=600),
        make_game("Roguelike", "roguelike", hltb_main_story_minutes=300, is_endless=True),
    ])
    pg_session.commit()

    def titles(**kw) -> set[str]:
        query = apply_advanced_filters(build_catalog_query("all", None, None, None, None, None, "all", "title", "asc"), CatalogFilters(**kw))
        return {game.title for game in pg_session.scalars(query).all()}

    assert titles(playtime_max_hours=60) == {"RDR2", "Only Provider"}  # 51 h via HLTB, not 100 h
    assert titles(playtime_min_hours=60) == set()
    assert titles(playtime_min_hours=5, playtime_max_hours=20) == {"Only Provider"}


@requires_postgres
def test_linux_filter_includes_proton_playable_tiers(pg_session) -> None:
    pg_session.add_all([
        make_game("Native", "native", platforms=["PC", "Linux"]),
        make_game("Proton Gold", "proton-gold", platforms=["PC"], proton_tier="gold"),
        make_game("Borked", "borked", platforms=["PC"], proton_tier="borked"),
    ])
    pg_session.commit()
    query = apply_advanced_filters(
        build_catalog_query("all", None, None, None, None, None, "all", "title", "asc"),
        CatalogFilters(platform="linux"),
    )
    assert {game.title for game in pg_session.scalars(query).all()} == {"Native", "Proton Gold"}


def test_steam_product_type_marks_dlc() -> None:
    game = make_game("Some Expansion", "some-expansion")
    assert content_type_from_steam_type("dlc") == "dlc"
    assert content_type_from_steam_type("music") == "soundtrack"
    assert content_type_from_steam_type("game") is None
    assert infer_content_type(game, steam_type="dlc") == "dlc"
    assert infer_content_type(game) == "game"


def test_date_classification() -> None:
    placeholder = make_game("FF7", release_year=1970, release_date=date(1970, 1, 1))
    assert classify(placeholder, date(2013, 7, 4)) == "unknown"
    reissue = make_game("Mass Effect", release_year=2021, release_date=date(2021, 5, 14))
    assert classify(reissue, date(2008, 5, 28)) == "earlier"
    remaster = make_game("Mass Effect Legendary Edition", release_year=2021, release_date=date(2021, 5, 14))
    assert classify(remaster, date(2008, 5, 28)) == "conflict"
    assert classify(make_game("Port", release_year=1997, release_date=date(1997, 1, 1)), date(2013, 1, 1)) == "conflict"
    assert classify(make_game("Same", release_year=2013, release_date=date(2013, 1, 1)), date(2013, 6, 1)) is None


@requires_postgres
def test_release_date_repair_dry_run_then_apply(pg_session) -> None:
    unknown = make_game("Hades", "hades", steam_app_id=1145360, release_year=1970, release_date=date(1970, 1, 1))
    wrong_app = make_game("Elden Ring", "elden-ring", steam_app_id=2622380, release_year=1970, release_date=date(1970, 1, 1))
    pg_session.add_all([unknown, wrong_app])
    pg_session.commit()
    table = {
        1145360: AppdetailsOutcome("ok", {"type": "game", "name": "Hades", "release_date": {"date": "Sep 17, 2020"}}),
        2622380: AppdetailsOutcome("ok", {"type": "game", "name": "ELDEN RING NIGHTREIGN", "release_date": {"date": "May 29, 2025"}}),
    }

    async def fetch(app_id: int) -> AppdetailsOutcome:
        return table[app_id]

    dry = asyncio.run(repair_release_dates(pg_session, apply=False, fetcher=fetch, delay_seconds=0))
    assert dry.counts == {"unknown": 1, "identity_mismatch": 1}
    pg_session.expire_all()
    assert pg_session.get(Game, unknown.id).release_year == 1970

    asyncio.run(repair_release_dates(pg_session, apply=True, fetcher=fetch, delay_seconds=0))
    pg_session.expire_all()
    assert pg_session.get(Game, unknown.id).release_date == date(2020, 9, 17)
    assert pg_session.get(Game, wrong_app.id).release_year == 1970  # wrong product: never written
