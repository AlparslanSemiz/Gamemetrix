"""Steam app id identity: verdicts, the claim guard, the single resolver, the audit."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.integrations.igdb_optional_metadata import extract_steam_app_id as igdb_steam_id
from app.integrations.steam import extract_steam_app_id, resolve_steam_app_id
from app.integrations.steam.client import AppdetailsOutcome
from app.integrations.steam.identity import identity_from_appdetails, steam_identity_verdict
from app.models import CatalogQualityReview, ExternalId, PriceSnapshot
from app.services.steam_id_audit import audit_steam_ids
from app.services.steam_identity import claim_steam_app_id

from .pg_support import make_game, pg_session, requires_postgres  # noqa: F401


@pytest.mark.parametrize(
    ("title", "year", "steam_name", "steam_year", "steam_type", "ok"),
    [
        ("Elden Ring", 2022, "ELDEN RING NIGHTREIGN", 2025, "game", False),
        ("Slay the Spire", 2019, "Slay the Spire 2", 2026, "game", False),
        ("Age of Empires II: Definitive Edition", 2019, "Age of Empires II (Retired)", 2013, "game", False),
        ("Call of Duty: Modern Warfare 3", 2011, "Call of Duty®: Modern Warfare® III", 2023, "game", False),
        ("Call of Duty: Modern Warfare 2", 2009, "Call of Duty®: Modern Warfare® 2 (2009)", 2009, "game", True),
        ("Call of Duty: Modern Warfare II", 2022, "Call of Duty®: Modern Warfare® II", 2022, "game", True),
        ("Kingdom Come: Deliverance II", 2025, "Some Dead Island DLC", 2025, "dlc", False),
        ("Hades", 2020, "Hades", 2020, "game", True),
        ("Hades", 2020, "Hades", 2020, "dlc", False),
    ],
)
def test_identity_verdict(title, year, steam_name, steam_year, steam_type, ok) -> None:
    verdict = steam_identity_verdict(
        title, year, steam_name=steam_name, steam_year=steam_year, steam_type=steam_type
    )
    assert verdict.ok is ok


def test_fullgame_parent_marks_an_app_as_dlc() -> None:
    data = {"type": "game", "name": "Hades", "fullgame": {"appid": 1, "name": "Hades"}}
    assert identity_from_appdetails("Hades", 2020, data).steam_type == "dlc"


def test_slug_suffix_is_not_a_steam_id() -> None:
    assert extract_steam_app_id("year-walk-730") is None
    assert extract_steam_app_id("https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg") == 620


def test_resolver_prefers_stored_id_over_everything_else() -> None:
    game = SimpleNamespace(
        steam_app_id=1245620,
        slug="elden-ring-730",
        cover_url="https://cdn.cloudflare.steamstatic.com/steam/apps/999/header.jpg",
        image_url=None,
    )
    assert resolve_steam_app_id(game, {"Steam": "111"}) == 1245620
    game.steam_app_id = None
    assert resolve_steam_app_id(game, {"Steam": "111"}) == 111
    assert resolve_steam_app_id(game) == 999


def test_igdb_cross_reference_must_name_the_same_product() -> None:
    raw = {"external_games": [
        {"category": 1, "uid": "2622380", "name": "ELDEN RING NIGHTREIGN"},
        {"category": 1, "uid": "1245620", "name": "ELDEN RING"},
    ]}
    assert igdb_steam_id(raw, title="Elden Ring", release_year=2022) == 1245620
    assert igdb_steam_id({"external_games": raw["external_games"][:1]}, title="Elden Ring") is None


@requires_postgres
def test_unverified_claim_never_replaces_an_existing_id(pg_session) -> None:
    game = make_game("Elden Ring", steam_app_id=1245620)
    pg_session.add(game)
    pg_session.flush()

    assert claim_steam_app_id(pg_session, game, 2622380, verified=False) is False
    assert game.steam_app_id == 1245620

    assert claim_steam_app_id(pg_session, game, 1245620, verified=True) is True
    assert game.steam_app_id_verified_at is not None
    # even an unverified claim for a *different* id is refused once verified
    assert claim_steam_app_id(pg_session, game, 2622380, verified=False) is False
    assert game.steam_app_id == 1245620


async def _no_sleep(_seconds: float) -> None:
    return None


def _fetcher(table: dict[int, AppdetailsOutcome]):
    async def fetch(app_id: int) -> AppdetailsOutcome:
        return table[app_id]
    return fetch


@requires_postgres
def test_audit_dry_run_reports_without_writing_then_apply_clears(pg_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.steam_id_audit.asyncio.sleep", _no_sleep)
    good = make_game("Hades", steam_app_id=1145360, release_year=2020)
    bad = make_game(
        "Elden Ring", steam_app_id=2622380, release_year=2022,
        source_scores=[
            {"source": "Steam", "score": 90, "status": "live", "review_count": 10},
            {"source": "Metacritic", "score": 96, "status": "live", "review_count": 50},
        ],
    )
    pg_session.add_all([good, bad])
    pg_session.flush()
    pg_session.add(PriceSnapshot(
        game_id=bad.id, source="Steam", store="Steam", region="US", currency="USD",
        list_price=10, sale_price=10, url="https://store.steampowered.com/app/2622380/",
        fetched_at=datetime.now(UTC), created_at=datetime.now(UTC),
    ))
    pg_session.commit()
    table = {
        1145360: AppdetailsOutcome("ok", {"type": "game", "name": "Hades", "release_date": {"date": "Sep 17, 2020"}}),
        2622380: AppdetailsOutcome("ok", {"type": "game", "name": "ELDEN RING NIGHTREIGN", "release_date": {"date": "May 29, 2025"}}),
    }

    report = asyncio.run(audit_steam_ids(pg_session, apply=False, fetcher=_fetcher(table), delay_seconds=0))
    assert report.counts == {"verified": 1, "mismatch": 1}
    pg_session.expire_all()
    assert pg_session.get(type(bad), bad.id).steam_app_id == 2622380  # dry-run wrote nothing
    assert pg_session.scalar(select(CatalogQualityReview)) is None

    report = asyncio.run(audit_steam_ids(pg_session, apply=True, fetcher=_fetcher(table), delay_seconds=0))
    assert report.counts == {"verified": 1, "mismatch": 1}
    pg_session.expire_all()
    cleared = pg_session.get(type(bad), bad.id)
    assert cleared.steam_app_id is None
    assert [row["source"] for row in cleared.source_scores] == ["Metacritic"]
    assert pg_session.scalars(select(PriceSnapshot)).all() == []
    review = pg_session.scalar(select(CatalogQualityReview))
    assert review.status == "needs_review" and "steam_id_mismatch" in review.signals
    assert pg_session.get(type(good), good.id).steam_app_id_verified_at is not None
    assert pg_session.scalars(select(ExternalId).where(ExternalId.game_id == bad.id)).all() == []


@requires_postgres
def test_audit_treats_outages_as_unknown_and_stops(pg_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.steam_id_audit.asyncio.sleep", _no_sleep)
    for index in range(7):
        pg_session.add(make_game(f"Game {index}", steam_app_id=1000 + index))
    pg_session.commit()
    table = {1000 + index: AppdetailsOutcome("error") for index in range(7)}
    report = asyncio.run(audit_steam_ids(pg_session, apply=True, fetcher=_fetcher(table), delay_seconds=0))
    assert report.counts == {"unknown": 5}
    assert report.stopped_early
    assert all(game.steam_app_id for game in pg_session.scalars(select(type(make_game("x")))).all())
