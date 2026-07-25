from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, JSON

from scripts.migrate_legacy_sqlite import coerce_value


def test_coerce_value_converts_legacy_json_text() -> None:
    column = Column("payload", JSON)

    assert coerce_value(column, '["PC", "Linux"]') == ["PC", "Linux"]
    assert coerce_value(column, "legacy malformed payload") == "legacy malformed payload"


def test_coerce_value_converts_sqlite_boolean_and_dates() -> None:
    assert coerce_value(Column("enabled", Boolean), 1) is True
    assert coerce_value(Column("released", Date), "2026-07-24") == date(2026, 7, 24)
    assert coerce_value(
        Column("fetched", DateTime(timezone=True)),
        "2026-07-24T10:30:00Z",
    ) == datetime(2026, 7, 24, 10, 30, tzinfo=UTC)
