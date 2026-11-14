"""The full-catalog completeness sweep must run in bounded memory.

Production runs it over ~50k games inside a 400 MiB container. It used to assign
`data_complete` on every row; SQLAlchemy marks a row modified on any assignment,
and the session holds modified rows strongly, so the whole catalog (summaries and
parsed `source_scores` included) piled up in the identity map until the kernel
OOM-killed the backend, every data-fill run, in a restart loop.
"""

import datetime

import pytest
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game
from app.services import completeness

_NOW = datetime.datetime.now(datetime.UTC)


def _placeholder(column):
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
        return _NOW.date()
    if isinstance(kind, DateTime):
        return _NOW
    return None


def _game(slug: str, *, data_complete: bool = False) -> Game:
    values = {
        column.name: _placeholder(column)
        for column in Game.__table__.columns
        if not column.nullable and column.default is None and not column.primary_key
    }
    values.update(
        title=slug,
        slug=slug,
        content_type="game",
        summary="A long enough description of the game. " * 20,
        summary_quality="ok",
        cover_url="https://example.com/cover.jpg",
        release_year=2020,
        platforms=["PC"],
        source_scores=[],
    )
    game = Game(**values)
    game.data_complete = data_complete
    return game


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def test_sweep_does_not_keep_the_catalog_in_the_session(engine, monkeypatch) -> None:
    total = completeness._SWEEP_BATCH * 3 + 17
    with Session(engine) as db:
        db.add_all([_game(f"game-{index}") for index in range(total)])
        db.commit()

    peak = 0
    real_compute = completeness.compute_data_complete

    with Session(engine) as db:
        def tracking_compute(game: Game) -> bool:
            nonlocal peak
            peak = max(peak, len(db.identity_map))
            return real_compute(game)

        monkeypatch.setattr(completeness, "compute_data_complete", tracking_compute)
        result = completeness.sweep_data_complete(db)

    assert result == {"complete": 0, "changed": 0}
    assert peak <= completeness._SWEEP_BATCH


def test_sweep_writes_only_changed_flags(engine, monkeypatch) -> None:
    with Session(engine) as db:
        db.add_all([
            _game("stays-incomplete"),
            _game("becomes-complete"),
            _game("stays-complete", data_complete=True),
            _game("becomes-incomplete", data_complete=True),
        ])
        db.commit()

    complete_slugs = {"becomes-complete", "stays-complete"}
    monkeypatch.setattr(
        completeness,
        "compute_data_complete",
        lambda game: game.id in complete_ids,
    )
    with Session(engine) as db:
        complete_ids = set(db.scalars(select(Game.id).where(Game.slug.in_(complete_slugs))))

    updates: list[str] = []

    def record_updates(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("UPDATE"):
            updates.append(statement)

    event.listen(engine, "before_cursor_execute", record_updates)
    with Session(engine) as db:
        result = completeness.sweep_data_complete(db)
    event.remove(engine, "before_cursor_execute", record_updates)

    assert result == {"complete": 2, "changed": 2}
    with Session(engine) as db:
        flags = {slug: flag for slug, flag in db.execute(select(Game.slug, Game.data_complete))}
    assert flags == {
        "stays-incomplete": False,
        "becomes-complete": True,
        "stays-complete": True,
        "becomes-incomplete": False,
    }
    # executemany may group both rows into one statement; never one per scanned row.
    assert 1 <= len(updates) <= 2
