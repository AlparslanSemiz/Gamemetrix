from datetime import UTC, datetime
from types import SimpleNamespace

from app.integrations.sync.persistence import _rating_snapshot, persist_source_records
from app.integrations.types import ExternalScore


class _FakeSession:
    def __init__(self, current) -> None:
        self.current = current
        self.added: list[object] = []

    def scalar(self, _statement):
        return self.current

    def add(self, row) -> None:
        self.added.append(row)


def _game():
    return SimpleNamespace(
        id=42,
        title="Stable Game",
        applicable_primary_sources=frozenset({"IGDB"}),
    )


def test_persist_source_records_skips_unchanged_audit_snapshots() -> None:
    game = _game()
    score = ExternalScore(
        source="IGDB",
        score=84,
        review_count=120,
        raw={"provider_value": 84},
    )
    current = _rating_snapshot(game, score, game.applicable_primary_sources, datetime.now(UTC))
    db = _FakeSession(current)

    persist_source_records(db, game, [score])

    assert db.added == []


def test_persist_source_records_keeps_meaningful_changes() -> None:
    game = _game()
    old_score = ExternalScore(source="IGDB", score=84, review_count=120)
    new_score = ExternalScore(source="IGDB", score=85, review_count=121)
    current = _rating_snapshot(
        game,
        old_score,
        game.applicable_primary_sources,
        datetime.now(UTC),
    )
    db = _FakeSession(current)

    persist_source_records(db, game, [new_score])

    assert len(db.added) == 2
