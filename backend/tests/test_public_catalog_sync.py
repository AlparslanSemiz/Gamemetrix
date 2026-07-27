from datetime import UTC, date, datetime

import pytest

from scripts.sync_public_catalog import _game_values


def test_game_values_keeps_public_columns_and_parses_temporal_values() -> None:
    values = _game_values(
        {
            "id": 99,
            "title": "Production Game",
            "slug": "production-game",
            "summary": "Summary",
            "cover_url": "https://example.com/cover.jpg",
            "release_date": "2026-07-27",
            "early_access_date": None,
            "metadata_refreshed_at": "2026-07-27T12:00:00Z",
            "genres": ["Action"],
            "live_primary_source_count": 3,
            "price_snapshots": [{"store": "Steam"}],
        }
    )

    assert values["release_date"] == date(2026, 7, 27)
    assert values["early_access_date"] is None
    assert values["metadata_refreshed_at"] == datetime(
        2026, 7, 27, 12, tzinfo=UTC
    )
    assert "id" not in values
    assert "live_primary_source_count" not in values
    assert "price_snapshots" not in values


def test_game_values_rejects_missing_required_public_fields() -> None:
    with pytest.raises(RuntimeError, match="required fields"):
        _game_values({"title": "Incomplete"})
