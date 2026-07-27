from datetime import date
from types import SimpleNamespace

from app.models import AiCatalogChange
from app.services.ai_catalog_changes import record_ai_catalog_change


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)


def test_ai_change_log_records_only_changed_fields_and_bounds_text() -> None:
    db = _Session()
    game = SimpleNamespace(id=7, title="Portal 2", slug="portal-2")

    row = record_ai_catalog_change(
        db,
        game,
        change_type="catalog_quality_repair",
        before={"release_year": 1970, "summary": "x" * 2_000, "developer": "Valve"},
        after={"release_year": date(2011, 4, 18), "summary": "y" * 2_000, "developer": "Valve"},
        reason="AI verified provider-backed metadata.",
    )

    assert isinstance(row, AiCatalogChange)
    assert row.fields == ["release_year", "summary"]
    assert row.before_values["release_year"] == 1970
    assert row.after_values["release_year"] == "2011-04-18"
    assert len(row.before_values["summary"]) == 1_000
    assert db.added == [row]


def test_ai_change_log_skips_noop_updates() -> None:
    db = _Session()
    game = SimpleNamespace(id=7, title="Portal 2", slug="portal-2")

    row = record_ai_catalog_change(
        db,
        game,
        change_type="summary_audit",
        before={"summary_quality": "ok"},
        after={"summary_quality": "ok"},
    )

    assert row is None
    assert db.added == []
