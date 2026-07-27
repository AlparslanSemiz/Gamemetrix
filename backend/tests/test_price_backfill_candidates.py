import datetime

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game, PriceSnapshot
from app.services.price_backfill import price_backfill_candidates

_NOW = datetime.datetime.now(datetime.UTC)
_TODAY = _NOW.date()


def _placeholder(column):
    """A type-appropriate zero value, so tests only state the fields they care about."""
    kind = column.type
    if isinstance(kind, Boolean):
        return False
    if isinstance(kind, Integer):
        return 0
    if isinstance(kind, Float):
        return 0.0
    if isinstance(kind, (String, Text)):
        return ""
    if isinstance(kind, Date) and not isinstance(kind, DateTime):
        return _TODAY
    if isinstance(kind, DateTime):
        return _NOW
    return None


def _game(slug: str, *, rank_score: float, prices_refreshed_at: datetime.datetime | None) -> Game:
    values = {
        column.name: _placeholder(column)
        for column in Game.__table__.columns
        if not column.nullable and column.default is None and not column.primary_key
    }
    values.update(
        title=slug,
        slug=slug,
        rank_score=rank_score,
        metrix_score=rank_score,
        content_type="game",
    )
    game = Game(**values)
    game.prices_refreshed_at = prices_refreshed_at
    return game


def _price_snapshot(game_id: int) -> PriceSnapshot:
    return PriceSnapshot(
        game_id=game_id,
        source="Steam",
        store="Steam",
        region="US",
        currency="USD",
        list_price=19.99,
        sale_price=9.99,
        url="https://store.steampowered.com/app/1/",
        fetched_at=_NOW,
        created_at=_NOW,
    )


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_sweep_reaches_games_buried_under_a_fully_fresh_top_pool(db: Session) -> None:
    """
    The old query took a fixed top-N-by-rank slice and filtered it in Python. Once
    that slice was fresh it yielded nothing, and the sweep never looked deeper — so
    anything below it was never priced. Put a full fresh pool above one stale game
    and it must still surface.
    """
    fresh_pool_size = 260  # larger than the old fixed slice
    for index in range(fresh_pool_size):
        game = _game(f"fresh-{index:03d}", rank_score=100.0 - index * 0.1, prices_refreshed_at=_NOW)
        db.add(game)
        db.flush()
        db.add(_price_snapshot(game.id))
    db.add(_game("stale-deep", rank_score=0.5, prices_refreshed_at=None))
    db.commit()

    assert [game.slug for game in price_backfill_candidates(db, 10)] == ["stale-deep"]


def test_candidates_stay_ordered_by_rank(db: Session) -> None:
    db.add_all([
        _game("low", rank_score=10.0, prices_refreshed_at=None),
        _game("high", rank_score=90.0, prices_refreshed_at=None),
        _game("mid", rank_score=50.0, prices_refreshed_at=None),
    ])
    db.commit()

    assert [game.slug for game in price_backfill_candidates(db, 10)] == ["high", "mid", "low"]


def test_limit_caps_the_batch(db: Session) -> None:
    db.add_all([
        _game(f"game-{index}", rank_score=float(index), prices_refreshed_at=None)
        for index in range(10)
    ])
    db.commit()

    assert len(price_backfill_candidates(db, 3)) == 3
