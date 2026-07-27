from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.admin_dashboard import (
    _catalog_additions,
    _fill_daily_catalog_addition_gaps,
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CatalogSession:
    def __init__(self, now: datetime):
        self._scalar_values = iter((3, 12, 40, 2))
        self._execute_values = iter(
            (
                _Rows(((now.date(), 3),)),
                _Rows(
                    (
                        SimpleNamespace(
                            id=7,
                            title="Fresh Game",
                            slug="fresh-game",
                            catalog_added_at=now,
                        ),
                    )
                ),
                _Rows(((7, "IGDB"), (7, "Steam"), (7, "Steam"))),
            )
        )

    def scalar(self, _statement):
        return next(self._scalar_values)

    def execute(self, _statement):
        return next(self._execute_values)


def test_catalog_additions_returns_counts_daily_gaps_and_recent_sources() -> None:
    now = datetime(2026, 7, 27, 12, tzinfo=UTC)

    additions = _catalog_additions(_CatalogSession(now), days=3, now=now)

    assert additions["last_24h"] == 3
    assert additions["last_7d"] == 12
    assert additions["last_30d"] == 40
    assert additions["untracked_games"] == 2
    assert additions["daily"] == [
        {"date": "2026-07-25", "count": 0},
        {"date": "2026-07-26", "count": 0},
        {"date": "2026-07-27", "count": 3},
    ]
    assert additions["recent"] == [
        {
            "id": 7,
            "title": "Fresh Game",
            "slug": "fresh-game",
            "added_at": "2026-07-27T12:00:00+00:00",
            "sources": ["IGDB", "Steam"],
        }
    ]


def test_daily_catalog_additions_includes_zero_days() -> None:
    now = datetime(2026, 7, 27, 12, tzinfo=UTC)

    rows = _fill_daily_catalog_addition_gaps(
        {"2026-07-26": 5},
        days=3,
        now=now,
    )

    assert rows == [
        {"date": "2026-07-25", "count": 0},
        {"date": "2026-07-26", "count": 5},
        {"date": "2026-07-27", "count": 0},
    ]
