"""Partitioned snapshot tables: ORM inserts, latest-row retention, quota-window purge."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import ApiRequestWindow, DataFillRun, RatingSnapshot, SourceSnapshot
from app.services import snapshot_retention as retention
from tests.pg_support import make_game, pg_session, requires_postgres  # noqa: F401

pytestmark = requires_postgres

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)


def _factory(session: Session):
    engine = session.get_bind()
    return lambda: Session(engine, expire_on_commit=False)


def _rating(game_id: int, source: str, when: datetime, score: float = 70.0) -> RatingSnapshot:
    return RatingSnapshot(
        game_id=game_id, source=source, score=score, score_normalized=score, rating_count=1,
        review_count=1, is_critic=False, is_user=True, is_applicable=True, confidence=1.0,
        raw_payload={"a": 1}, fetched_at=when, created_at=when,
    )


def _source(external_id: str | None, when: datetime, query: str = "q") -> SourceSnapshot:
    return SourceSnapshot(
        source="IGDB", endpoint="e", query=query, external_id=external_id, raw_payload={},
        fetched_at=when, created_at=when,
    )


def test_orm_inserts_get_ids_and_cascade_from_games(pg_session) -> None:
    game = make_game("Cascade", "cascade")
    pg_session.add(game)
    pg_session.flush()
    row = _rating(game.id, "IGDB", datetime.now(UTC))
    pg_session.add(row)
    pg_session.commit()
    assert row.id is not None
    pg_session.delete(game)
    pg_session.commit()
    assert pg_session.scalar(select(func.count(RatingSnapshot.id))) == 0


def test_sweep_keeps_recent_and_latest_per_key_and_drops_the_rest(pg_session) -> None:
    game = make_game("Kept", "kept")
    pg_session.add(game)
    pg_session.flush()
    old_month = datetime(2026, 8, 10, tzinfo=UTC)
    pg_session.execute(text(
        "CREATE TABLE rating_snapshots_p202608 PARTITION OF rating_snapshots "
        "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')"))
    pg_session.execute(text(
        "CREATE TABLE source_snapshots_p202608 PARTITION OF source_snapshots "
        "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')"))
    pg_session.add_all([
        _rating(game.id, "IGDB", old_month, 1),                         # superseded
        _rating(game.id, "IGDB", old_month + timedelta(days=1), 2),     # newest IGDB, old -> kept
        _rating(game.id, "Steam", old_month, 3),                        # superseded by Nov row
        _rating(game.id, "Steam", NOW - timedelta(days=1), 4),          # makes the Aug Steam row stale
        _source("1", old_month), _source("1", old_month + timedelta(days=1)),
        _source(None, old_month, "t"), _source("2", old_month),
    ])
    pg_session.commit()

    summary = retention.run_snapshot_retention(_factory(pg_session), NOW)
    assert "rating_snapshots_p202608" in summary["rating_snapshots_dropped"]

    scores = sorted(pg_session.scalars(select(RatingSnapshot.score)))
    assert scores == [2.0, 4.0]  # Aug Steam row is superseded by the November one
    assert pg_session.scalar(select(func.count(SourceSnapshot.id))) == 3  # "1" latest, None, "2"

    retention.run_snapshot_retention(_factory(pg_session), NOW)  # idempotent
    assert pg_session.scalar(select(func.count(SourceSnapshot.id))) == 3


def test_ensure_partitions_is_idempotent_and_inserts_route_to_them(pg_session) -> None:
    factory = _factory(pg_session)
    with factory() as db:
        first = retention.ensure_partitions(db, "rating_snapshots", NOW)
        db.commit()
    with factory() as db:
        assert retention.ensure_partitions(db, "rating_snapshots", NOW) == []
    assert "rating_snapshots_p202611" in first and "rating_snapshots_p202702" in first


def test_quota_windows_and_data_fill_runs_are_trimmed(pg_session) -> None:
    now = NOW
    pg_session.add_all([
        ApiRequestWindow(source="OpenCritic", window_kind="rolling", window_start=now - timedelta(days=5),
                         window_seconds=1, request_count=1, request_limit=4, updated_at=now),
        ApiRequestWindow(source="RAWG", window_kind="monthly", window_start=now - timedelta(days=20),
                         window_seconds=31 * 86400, request_count=1, request_limit=9, updated_at=now),
    ])
    for index in range(7):
        pg_session.add(DataFillRun(status="done", force=False, target_total=1, result={"big": "x" * 50},
                                   started_at=now - timedelta(hours=index)))
    pg_session.commit()
    with _factory(pg_session)() as db:
        assert retention.purge_api_request_windows(db, now) == 1
    with _factory(pg_session)() as db:
        assert retention.trim_data_fill_runs(db) == 2
    assert pg_session.scalar(select(func.count(ApiRequestWindow.id))) == 1
    assert pg_session.scalar(text("SELECT count(*) FROM data_fill_runs WHERE result::text = '{}'")) == 2
