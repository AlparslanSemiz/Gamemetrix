"""Maintenance jobs under production-like Postgres timeouts.

Production runs with `idle_in_transaction_session_timeout=60s` server-wide and an 8 s /
15 min `statement_timeout` per pool. The fixtures here shrink the idle timeout to 300 ms
and make every Steam/ProtonDB fetch take longer than that: a job that keeps a transaction
open across a fetch gets its connection terminated, exactly as `fix_release_dates` did.
"""

import asyncio
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from app.integrations.protondb import ProtonSummary
from app.integrations.steam.client import AppdetailsOutcome
from app.models import CatalogQualityReview, Game
from app.services.deduplication import consolidate_duplicate_games, preview_duplicate_groups
from app.services.deduplication.store import duplicate_group_game_ids, find_duplicate_id_groups
from app.services.protondb_refresh import refresh_proton_tiers
from app.services.release_date_repair import repair_release_dates
from app.services.steam_id_audit import audit_steam_ids

from .pg_support import TEST_DATABASE_URL, make_game, pg_session, requires_postgres  # noqa: F401

IDLE_TIMEOUT_MS = 300
FETCH_SECONDS = 0.6  # > IDLE_TIMEOUT_MS: an open transaction would be killed mid-fetch


@pytest.fixture()
def strict_session(pg_session):  # noqa: F811
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={
            "options": f"-c idle_in_transaction_session_timeout={IDLE_TIMEOUT_MS} -c statement_timeout=5000"
        },
    )
    with Session(engine, autoflush=False) as session:
        assert session.scalar(text("SHOW idle_in_transaction_session_timeout")) == f"{IDLE_TIMEOUT_MS}ms"
        session.rollback()
        yield session
    engine.dispose()


def _slow(session: Session, table: dict):
    """A fetcher that fails the test if the job holds a transaction while it waits."""
    seen: list[int] = []

    async def fetch(app_id: int):
        assert not session.in_transaction(), "transaction open during a network call"
        seen.append(app_id)
        await asyncio.sleep(FETCH_SECONDS)
        return table[app_id]

    fetch.seen = seen  # type: ignore[attr-defined]
    return fetch


def _steam(name: str, released: str) -> AppdetailsOutcome:
    return AppdetailsOutcome("ok", {"type": "game", "name": name, "release_date": {"date": released}})


@requires_postgres
def test_release_date_repair_survives_idle_timeout(pg_session, strict_session) -> None:
    rows = [
        make_game("Hades", "hades", steam_app_id=1145360, release_year=1970, release_date=date(1970, 1, 1)),
        make_game("Celeste", "celeste", steam_app_id=504230, release_year=1970, release_date=date(1970, 1, 1)),
        make_game("Elden Ring", "elden-ring", steam_app_id=2622380, release_year=1970, release_date=date(1970, 1, 1)),
    ]
    pg_session.add_all(rows)
    pg_session.commit()
    table = {
        1145360: _steam("Hades", "Sep 17, 2020"),
        504230: _steam("Celeste", "Jan 25, 2018"),
        2622380: _steam("ELDEN RING NIGHTREIGN", "May 29, 2025"),
    }

    fetch = _slow(strict_session, table)
    dry = asyncio.run(repair_release_dates(
        strict_session, apply=False, fetcher=fetch, delay_seconds=0, batch_size=2
    ))
    assert dry.checked == 3 and fetch.seen == [row.steam_app_id for row in rows]  # all batches walked
    assert dry.counts == {"unknown": 2, "identity_mismatch": 1}
    assert pg_session.scalar(select(Game.release_year).where(Game.slug == "hades")) == 1970

    asyncio.run(repair_release_dates(
        strict_session, apply=True, fetcher=_slow(strict_session, table), delay_seconds=0,
        batch_size=2, commit_every=1,
    ))
    pg_session.expire_all()
    assert pg_session.scalar(select(Game.release_date).where(Game.slug == "hades")) == date(2020, 9, 17)
    assert pg_session.scalar(select(Game.release_year).where(Game.slug == "celeste")) == 2018
    assert pg_session.scalar(select(Game.release_year).where(Game.slug == "elden-ring")) == 1970


@requires_postgres
def test_steam_audit_survives_idle_timeout(pg_session, strict_session) -> None:
    pg_session.add_all([
        make_game("Hades", steam_app_id=1145360, release_year=2020),
        make_game("Celeste", steam_app_id=504230, release_year=2018),
        make_game("Elden Ring", steam_app_id=2622380, release_year=2022),
    ])
    pg_session.commit()
    table = {
        1145360: _steam("Hades", "Sep 17, 2020"),
        504230: _steam("Celeste", "Jan 25, 2018"),
        2622380: _steam("ELDEN RING NIGHTREIGN", "May 29, 2025"),
    }

    dry = asyncio.run(audit_steam_ids(
        strict_session, apply=False, fetcher=_slow(strict_session, table), delay_seconds=0, batch_size=2
    ))
    assert dry.counts == {"verified": 2, "mismatch": 1}
    assert pg_session.scalar(select(CatalogQualityReview)) is None

    applied = asyncio.run(audit_steam_ids(
        strict_session, apply=True, fetcher=_slow(strict_session, table), delay_seconds=0,
        batch_size=2, commit_every=2,
    ))
    assert applied.counts == {"verified": 2, "mismatch": 1}
    assert applied.last_id == max(pg_session.scalars(select(Game.id)))
    pg_session.expire_all()
    assert pg_session.scalar(select(Game.steam_app_id).where(Game.title == "Elden Ring")) is None
    assert pg_session.scalar(select(Game.steam_app_id_verified_at).where(Game.title == "Hades")) is not None


@requires_postgres
def test_protondb_refresh_survives_idle_timeout(pg_session, strict_session, monkeypatch) -> None:
    monkeypatch.setattr("app.services.protondb_refresh.MIN_DELAY_SECONDS", 0)
    verified = datetime.now(UTC)
    pg_session.add_all([
        make_game("A", steam_app_id=10, steam_app_id_verified_at=verified),
        make_game("B", steam_app_id=20, steam_app_id_verified_at=verified),
    ])
    pg_session.commit()
    fetch = _slow(strict_session, {10: ProtonSummary("ok", "gold", 0.8), 20: ProtonSummary("no_reports")})

    result = asyncio.run(refresh_proton_tiers(strict_session, limit=10, delay_seconds=0, fetcher=fetch))
    assert result == {"updated": 1, "unchanged": 0, "no_reports": 1, "errors": 0}
    pg_session.expire_all()
    assert pg_session.scalar(select(Game.proton_tier).where(Game.title == "A")) == "gold"
    assert all(pg_session.scalars(select(Game.proton_refreshed_at)))


def _duplicates(pg_session) -> None:  # noqa: F811
    pg_session.add_all([
        make_game("Portal 2", "portal-2", release_year=2011, developer="Valve", summary="x" * 200),
        make_game("Portal II", "portal-ii-4412", release_year=2011),
        make_game("Hades", "hades", release_year=2020),
        make_game("Celeste", "celeste", release_year=2018),
        make_game("Celeste", "celeste-2", release_year=2018),
    ])
    pg_session.commit()


@requires_postgres
def test_duplicate_scan_pages_by_id(pg_session) -> None:
    _duplicates(pg_session)
    paged = find_duplicate_id_groups(pg_session, batch_size=2)
    assert sorted(map(sorted, paged)) == sorted(map(sorted, find_duplicate_id_groups(pg_session)))
    assert len(paged) == 2


@requires_postgres
def test_consolidation_dry_run_selects_only_the_columns_it_needs(pg_session) -> None:
    """Regression: the dry run loaded every column of the whole catalog in one SELECT."""
    _duplicates(pg_session)
    statements: list[str] = []

    def capture(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    event.listen(pg_session.bind, "before_cursor_execute", capture)
    try:
        report = consolidate_duplicate_games(pg_session, dry_run=True)
        preview = preview_duplicate_groups(pg_session)
        ids = duplicate_group_game_ids(pg_session)
    finally:
        event.remove(pg_session.bind, "before_cursor_execute", capture)

    assert report["merged_groups"] == 2 and report["removed"] == 2
    assert {group["keeper"]["slug"] for group in report["groups"]} == {"portal-2", "celeste"}
    assert len(preview) == 2 and len(ids) == 4

    game_selects = [s for s in statements if s.lstrip().upper().startswith("SELECT") and "FROM games" in s]
    scans = [s for s in game_selects if " IN (" not in s]
    assert scans, "expected keyset scans over games"
    for statement in scans:
        assert "LIMIT" in statement, statement  # every catalog-wide read is a bounded batch
        for blob in ("source_scores", "screenshots", "system_requirements", "similar_games", "dlcs", "summary"):
            assert f"games.{blob}" not in statement, statement
    keeper_loads = [s for s in game_selects if " IN (" in s]
    assert keeper_loads, "expected grouped rows loaded by id"
    for statement in keeper_loads:
        for blob in ("system_requirements", "similar_games", "dlcs", "awards"):
            assert f"games.{blob}" not in statement, statement
