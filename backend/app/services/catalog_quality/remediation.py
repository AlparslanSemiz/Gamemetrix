"""Pure field selection and reversible application of researched metadata repairs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from ...integrations.title_matching import normalize_title
from ...integrations.types import NormalizedGame
from ...models import Game
from ..metadata import clean_game_summary

_SOURCE_PRIORITY = {
    "IGDB": 5,
    "Wikidata": 4,
    "RAWG": 3,
    "Steam": 2,
    "GameBrain": 1,
}
_MAX_GENRES = 6
_MAX_PLATFORMS = 12
_MAX_NAME_CHARS = 200
_EARLIEST_MEANINGFUL_YEAR = 1970

_SIGNAL_FIELDS: dict[str, frozenset[str]] = {
    "suspicious_title": frozenset({"title"}),
    "malformed_title": frozenset({"title"}),
    "weak_summary": frozenset({"summary"}),
    "raw_html_summary": frozenset({"summary"}),
    "placeholder_summary": frozenset({"summary"}),
    "encoding_corruption": frozenset({"summary"}),
    "summary_shared_with_other_titles": frozenset({"summary"}),
    "missing_core_metadata": frozenset({"genres", "platforms", "developer", "publisher"}),
    "unknown_release_with_weak_metadata": frozenset({"release_year"}),
    "malformed_structured_metadata": frozenset({"genres", "platforms", "developer", "publisher"}),
}
_REPAIRABLE_FIELDS = frozenset(
    {"title", "summary", "release_year", "genres", "platforms", "developer", "publisher"}
)


@dataclass(frozen=True)
class ResearchedGame:
    record: NormalizedGame
    trusted_identity: bool


@dataclass(frozen=True)
class RepairPlan:
    changes: dict[str, object]
    sources: dict[str, str]


@dataclass(frozen=True)
class RepairSnapshot:
    title: str
    summary: str
    summary_short: str | None
    summary_refreshed_at: datetime | None
    release_date: date
    release_year: int
    official_release_date: date | None
    genres: list[str]
    platforms: list[str]
    developer: str | None
    publisher: str | None
    metadata_refreshed_at: datetime | None
    data_complete: bool


def repair_fields(signals: list[str]) -> set[str]:
    fields: set[str] = set()
    for signal in signals:
        if signal.startswith("ai:"):
            field = signal.removeprefix("ai:")
            if field in _REPAIRABLE_FIELDS:
                fields.add(field)
            continue
        fields.update(_SIGNAL_FIELDS.get(signal, ()))
    return fields


def build_repair_plan(
    game: Game,
    signals: list[str],
    researched: list[ResearchedGame],
) -> RepairPlan:
    fields = repair_fields(signals)
    eligible = _identity_records(game, fields, researched)
    changes: dict[str, object] = {}
    sources: dict[str, str] = {}
    if not eligible:
        return RepairPlan(changes=changes, sources=sources)

    repaired_title = game.title
    if "title" in fields:
        selected = _preferred(eligible, lambda item: item.record.name)
        if selected and selected.record.name.strip() != game.title:
            repaired_title = selected.record.name.strip()[:160]
            changes["title"] = repaired_title
            sources["title"] = selected.record.source

    if "summary" in fields:
        summary_options: list[tuple[ResearchedGame, str]] = []
        for item in eligible:
            cleaned = clean_game_summary(item.record.summary, repaired_title)
            if cleaned:
                summary_options.append((item, cleaned))
        if summary_options:
            item, summary = max(
                summary_options,
                key=lambda pair: (_priority(pair[0]), len(pair[1])),
            )
            if summary != game.summary:
                changes["summary"] = summary
                sources["summary"] = item.record.source

    if "release_year" in fields:
        selected = _preferred(
            eligible,
            lambda item: (
                item.record.release_date
                if item.record.release_date
                and item.record.release_date.year > _EARLIEST_MEANINGFUL_YEAR
                else None
            ),
        )
        if selected and selected.record.release_date:
            released = selected.record.release_date
            if released != game.release_date or released.year != game.release_year:
                changes["release_date"] = released
                changes["release_year"] = released.year
                changes["official_release_date"] = released
                sources["release_year"] = selected.record.source

    _add_list_change(changes, sources, game, eligible, "genres", _MAX_GENRES, fields)
    _add_list_change(changes, sources, game, eligible, "platforms", _MAX_PLATFORMS, fields)
    _add_text_change(changes, sources, game, eligible, "developer", fields)
    _add_text_change(changes, sources, game, eligible, "publisher", fields)
    return RepairPlan(changes=changes, sources=sources)


def _identity_records(
    game: Game,
    fields: set[str],
    researched: list[ResearchedGame],
) -> list[ResearchedGame]:
    groups: dict[str, list[ResearchedGame]] = {}
    for item in researched:
        key = normalize_title(item.record.name)
        if key:
            groups.setdefault(key, []).append(item)
    if not groups:
        return []

    current_key = normalize_title(game.title)
    if "title" not in fields:
        return groups.get(current_key, [])

    consensus = [
        group
        for group in groups.values()
        if len({item.record.source for item in group}) >= 2
    ]
    if not consensus:
        return []
    return max(
        consensus,
        key=lambda group: (
            len({item.record.source for item in group}),
            sum(1 for item in group if item.trusted_identity),
            max(_priority(item) for item in group),
        ),
    )


def _preferred(
    records: list[ResearchedGame],
    value: Callable[[ResearchedGame], object],
) -> ResearchedGame | None:
    available = [item for item in records if value(item)]
    return max(available, key=_priority) if available else None


def _priority(item: ResearchedGame) -> tuple[int, int]:
    return (
        _SOURCE_PRIORITY.get(item.record.source, 0),
        1 if item.trusted_identity else 0,
    )


def _add_list_change(
    changes: dict[str, object],
    sources: dict[str, str],
    game: Game,
    records: list[ResearchedGame],
    field: str,
    limit: int,
    requested: set[str],
) -> None:
    if field not in requested:
        return
    selected = _preferred(records, lambda item: getattr(item.record, field))
    if selected is None:
        return
    values = [
        value[:100]
        for value in getattr(selected.record, field)
        if isinstance(value, str) and value.strip()
    ][:limit]
    if values and values != getattr(game, field):
        changes[field] = values
        sources[field] = selected.record.source


def _add_text_change(
    changes: dict[str, object],
    sources: dict[str, str],
    game: Game,
    records: list[ResearchedGame],
    field: str,
    requested: set[str],
) -> None:
    if field not in requested:
        return
    selected = _preferred(records, lambda item: getattr(item.record, field))
    if selected is None:
        return
    value = getattr(selected.record, field)
    if isinstance(value, str) and value.strip() and value.strip() != getattr(game, field):
        changes[field] = value.strip()[:_MAX_NAME_CHARS]
        sources[field] = selected.record.source


def apply_repair_plan(game: Game, plan: RepairPlan, now: datetime) -> RepairSnapshot:
    snapshot = _snapshot(game)
    if title := plan.changes.get("title"):
        game.title = str(title)
    if summary := plan.changes.get("summary"):
        game.summary = str(summary)
        game.summary_short = None
        game.summary_refreshed_at = None
    released = plan.changes.get("release_date")
    if isinstance(released, date):
        game.release_date = released
        game.release_year = released.year
        game.official_release_date = released
    for field in ("genres", "platforms"):
        values = plan.changes.get(field)
        if isinstance(values, list):
            setattr(game, field, list(values))
    for field in ("developer", "publisher"):
        value = plan.changes.get(field)
        if isinstance(value, str):
            setattr(game, field, value)
    game.metadata_refreshed_at = now
    game.data_complete = False
    return snapshot


def restore_repair(game: Game, snapshot: RepairSnapshot) -> None:
    game.title = snapshot.title
    game.summary = snapshot.summary
    game.summary_short = snapshot.summary_short
    game.summary_refreshed_at = snapshot.summary_refreshed_at
    game.release_date = snapshot.release_date
    game.release_year = snapshot.release_year
    game.official_release_date = snapshot.official_release_date
    game.genres = list(snapshot.genres)
    game.platforms = list(snapshot.platforms)
    game.developer = snapshot.developer
    game.publisher = snapshot.publisher
    game.metadata_refreshed_at = snapshot.metadata_refreshed_at
    game.data_complete = snapshot.data_complete


def _snapshot(game: Game) -> RepairSnapshot:
    return RepairSnapshot(
        title=game.title,
        summary=game.summary,
        summary_short=game.summary_short,
        summary_refreshed_at=game.summary_refreshed_at,
        release_date=game.release_date,
        release_year=game.release_year,
        official_release_date=game.official_release_date,
        genres=list(game.genres or []),
        platforms=list(game.platforms or []),
        developer=game.developer,
        publisher=game.publisher,
        metadata_refreshed_at=game.metadata_refreshed_at,
        data_complete=game.data_complete,
    )
