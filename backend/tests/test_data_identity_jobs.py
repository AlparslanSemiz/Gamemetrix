"""Duplicate consolidation (dry-run, redirects, id travel), ProtonDB refresh,
freshness stamps, refresh priority."""

import asyncio
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations.protondb import ProtonSummary, parse_summary
from app.integrations.sync.priority import (
    rating_refresh_priority,
    refresh_counts,
    top_refresh_candidates,
)
from app.integrations.types import ExternalScore
from app.models import ExternalId, Game, SlugRedirect
from app.services.deduplication import consolidate_duplicate_games
from app.services.price_backfill import _price_refresh_counts
from app.services.protondb_refresh import refresh_proton_tiers

from .pg_support import make_game, pg_session, requires_postgres  # noqa: F401


def _pair(pg_session, *, duplicate_verified: bool):
    keeper = make_game("Portal 2", "portal-2", release_year=2011, developer="Valve", summary="x" * 200)
    duplicate = make_game(
        "Portal II", "portal-ii-4412", release_year=2011, steam_app_id=620,
        steam_app_id_verified_at=datetime.now(UTC) if duplicate_verified else None,
    )
    pg_session.add_all([keeper, duplicate])
    pg_session.flush()
    pg_session.add(ExternalId(
        game_id=duplicate.id, source="Steam", external_id="620", confidence=0.85,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    ))
    pg_session.commit()
    return keeper, duplicate


@requires_postgres
def test_consolidation_dry_run_changes_nothing(pg_session) -> None:
    _pair(pg_session, duplicate_verified=False)
    report = consolidate_duplicate_games(pg_session, dry_run=True)
    assert report["dry_run"] is True and report["removed"] == 1
    assert report["groups"][0]["keeper"]["slug"] == "portal-2"
    assert len(pg_session.scalars(select(Game)).all()) == 2
    assert pg_session.scalars(select(SlugRedirect)).all() == []


@requires_postgres
def test_consolidation_redirects_old_slug_and_drops_unverified_steam_id(pg_session) -> None:
    keeper, duplicate = _pair(pg_session, duplicate_verified=False)
    keeper_id, old_slug = keeper.id, duplicate.slug
    result = consolidate_duplicate_games(pg_session)
    assert result["removed"] == 1
    pg_session.expire_all()
    merged = pg_session.get(Game, keeper_id)
    assert merged.steam_app_id is None  # unverified id did not travel
    assert pg_session.scalars(select(ExternalId).where(ExternalId.source == "Steam")).all() == []
    redirect = pg_session.get(SlugRedirect, old_slug)
    assert redirect is not None and redirect.game_id == keeper_id


@requires_postgres
def test_consolidation_carries_a_verified_steam_id(pg_session) -> None:
    keeper, _duplicate = _pair(pg_session, duplicate_verified=True)
    keeper_id = keeper.id
    consolidate_duplicate_games(pg_session)
    pg_session.expire_all()
    merged = pg_session.get(Game, keeper_id)
    assert merged.steam_app_id == 620 and merged.steam_app_id_verified_at is not None
    assert [row.external_id for row in pg_session.scalars(select(ExternalId)).all()] == ["620"]


@requires_postgres
def test_detail_endpoint_answers_301_for_a_merged_slug(pg_session) -> None:
    from app.database import get_db
    from app.main import app

    keeper, duplicate = _pair(pg_session, duplicate_verified=False)
    consolidate_duplicate_games(pg_session)
    app.dependency_overrides[get_db] = lambda: pg_session
    try:
        client = TestClient(app)
        response = client.get("/api/games/portal-ii-4412", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"] == "/api/games/portal-2"
        assert client.get("/api/games/no-such-game").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_protondb_summary_parsing() -> None:
    assert parse_summary({"tier": "gold", "score": 0.71}) == ProtonSummary("ok", "gold", 0.71)
    assert parse_summary({"tier": "pending"}).status == "no_reports"
    assert parse_summary([]).status == "error"


@requires_postgres
def test_protondb_refresh_queries_only_verified_ids_and_stamps(pg_session) -> None:
    verified = make_game("Verified", steam_app_id=10, steam_app_id_verified_at=datetime.now(UTC), proton_tier="silver")
    unverified = make_game("Unverified", steam_app_id=20)
    no_id = make_game("No Id")
    pg_session.add_all([verified, unverified, no_id])
    pg_session.commit()
    asked: list[int] = []

    async def fetch(app_id: int) -> ProtonSummary:
        asked.append(app_id)
        return ProtonSummary("ok", "gold", 0.8)

    result = asyncio.run(refresh_proton_tiers(pg_session, limit=10, delay_seconds=0, fetcher=fetch))
    assert asked == [10]
    assert result["updated"] == 1
    pg_session.expire_all()
    row = pg_session.get(Game, verified.id)
    assert (row.proton_tier, row.proton_score) == ("gold", 0.8)
    assert row.proton_refreshed_at is not None
    assert pg_session.get(Game, unverified.id).proton_refreshed_at is None

    # fresh rows are not asked again within the week; errors leave the stamp alone
    asked.clear()
    asyncio.run(refresh_proton_tiers(pg_session, limit=10, delay_seconds=0, fetcher=fetch))
    assert asked == []


@requires_postgres
def test_protondb_errors_do_not_stamp(pg_session) -> None:
    game = make_game("Flaky", steam_app_id=10, steam_app_id_verified_at=datetime.now(UTC))
    pg_session.add(game)
    pg_session.commit()

    async def fetch(_app_id: int) -> ProtonSummary:
        return ProtonSummary("error")

    result = asyncio.run(refresh_proton_tiers(pg_session, limit=5, delay_seconds=0, fetcher=fetch))
    assert result["errors"] == 1
    pg_session.expire_all()
    assert pg_session.get(Game, game.id).proton_refreshed_at is None


def test_budget_and_transport_failures_do_not_count_as_a_refresh() -> None:
    unavailable = lambda detail: ExternalScore(source="OpenCritic", score=0, status="unavailable", detail=detail)  # noqa: E731
    assert not refresh_counts([
        unavailable("OpenCritic request budget is too low for a complete lookup."),
        unavailable("IGDB is not configured."),
        unavailable("Steam request failed (ConnectError)."),
        unavailable("Steam rate limit reached."),
    ])
    assert refresh_counts([unavailable("No Steam App ID found for this game.")])
    assert refresh_counts([ExternalScore(source="Steam", score=80)])
    assert _price_refresh_counts(rows=True, aggregator_attempted=False)
    assert not _price_refresh_counts(rows=False, aggregator_attempted=False)


def _stale(title: str, **overrides) -> Game:
    return make_game(title, **{"platforms": ["PC"], "ratings_refreshed_at": None, **overrides})


def test_new_big_release_outranks_an_old_game_that_only_needs_a_recheck() -> None:
    now = datetime.now(UTC)
    new_release = _stale("Silksong", release_date=(now - timedelta(days=20)).date(), release_year=now.year)
    old_scored = _stale(
        "Old Favourite", release_date=date(2012, 1, 1), release_year=2012, metrix_score=70, rank_score=70,
        ratings_refreshed_at=now - timedelta(days=9),
        source_scores=[
            {"source": s, "score": 70, "status": "live", "review_count": 100}
            for s in ("Metacritic", "OpenCritic", "IGDB", "Steam")
        ],
    )
    assert rating_refresh_priority(new_release, now) > rating_refresh_priority(old_scored, now)


def test_top_candidates_respects_limit_and_order() -> None:
    now = datetime.now(UTC)
    games = [
        _stale("A", release_date=date(2010, 1, 1), release_year=2010),
        _stale("B", release_date=(now - timedelta(days=5)).date(), release_year=now.year),
    ]
    for index, game in enumerate(games, start=1):
        game.id = index
    assert top_refresh_candidates(games, limit=1) == [2]


@requires_postgres
def test_consolidation_keeps_users_lists(pg_session) -> None:
    from app.models import User, UserCollection

    keeper, duplicate = _pair(pg_session, duplicate_verified=False)
    keeper_id = keeper.id
    now = datetime.now(UTC)
    for uid in ("u-both", "u-dup"):
        pg_session.add(User(id=uid, email=f"{uid}@example.com", display_name=uid, created_at=now, updated_at=now))
    pg_session.flush()
    pg_session.add_all([
        UserCollection(user_id="u-both", game_id=keeper.id, collection_type="wishlist", created_at=now),
        UserCollection(user_id="u-both", game_id=duplicate.id, collection_type="wishlist", created_at=now),
        UserCollection(user_id="u-dup", game_id=duplicate.id, collection_type="wishlist", created_at=now),
        UserCollection(user_id="u-dup", game_id=duplicate.id, collection_type="played", created_at=now),
    ])
    pg_session.flush()

    consolidate_duplicate_games(pg_session)
    pg_session.expire_all()

    rows = pg_session.execute(
        select(UserCollection.user_id, UserCollection.game_id, UserCollection.collection_type)
    ).all()
    assert sorted(rows) == sorted([
        ("u-both", keeper_id, "wishlist"),
        ("u-dup", keeper_id, "wishlist"),
        ("u-dup", keeper_id, "played"),
    ])
