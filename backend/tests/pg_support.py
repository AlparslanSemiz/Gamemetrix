"""PostgreSQL fixtures and a Game builder shared by the data-identity tests.

Skipped unless TEST_DATABASE_URL names a database ending in `_test`.
"""

import datetime
import os

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Game

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
DATABASE_NAME = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?", 1)[0]
requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL or not DATABASE_NAME.endswith("_test"),
    reason="Set TEST_DATABASE_URL to a PostgreSQL database whose name ends with _test.",
)

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
    if isinstance(kind, DateTime):
        return _NOW
    if isinstance(kind, Date):
        return _NOW.date()
    return None


def make_game(title: str, slug: str | None = None, **overrides) -> Game:
    """A valid Game row; tests state only the fields they care about."""
    values = {
        column.name: _placeholder(column)
        for column in Game.__table__.columns
        if not column.nullable and column.default is None and not column.primary_key
        and column.server_default is None
    }
    values.update(
        title=title,
        slug=slug or title.lower().replace(" ", "-"),
        summary="",
        cover_url="",
        release_date=datetime.date(2020, 1, 1),
        release_year=2020,
        genres=[],
        platforms=["PC"],
        source_scores=[],
        content_type="game",
    )
    values.update(overrides)
    return Game(**values)


@pytest.fixture()
def pg_session():
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False, autoflush=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
