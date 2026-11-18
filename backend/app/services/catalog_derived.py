"""Stored, query-ready columns derived from a game's JSON fields.

The catalog used to rebuild these per row with jsonb_array_elements sub-queries
on every sort and filter (6-8 s on 52k rows). They are now plain columns on
`games`, recomputed by one pure function that the Game before_insert /
before_update hooks call, so every writer (rescore, refresh, backfills, the
Steam audit purge, merge) stays consistent without remembering to.

Migration 20261119_0022 backfills existing rows with an SQL statement that
mirrors `derive_catalog_columns`; tests/test_catalog_derived.py asserts both
agree. Change one, change the other (and add a new migration, never edit 0022).
"""

from collections.abc import Iterable, Mapping
from typing import Any

from ..integrations.source_registry import CRITIC_SOURCES, PC_PLATFORM_KEYS, PRIMARY_SOURCES

MAX_REVIEW_COUNT = 2_000_000_000
MAX_VALID_SCORE = 100

# Canonical player-mode keys; the genre aliases cover catalogs that predate game_modes.
PLAYER_MODE_GENRE_ALIASES: dict[str, frozenset[str]] = {
    "multiplayer": frozenset({"massively multiplayer", "mmo", "mmorpg", "mmoarpg", "multiplayer", "pvp", "online co-op"}),
    "coop": frozenset({"co-op", "coop", "online co-op", "local co-op"}),
    "singleplayer": frozenset({"single player", "singleplayer"}),
}

# Umbrella platform tags: substring of a lower-cased platform name -> tag.
_PLATFORM_UMBRELLAS: tuple[tuple[str, str], ...] = (
    ("playstation", "playstation"),
    ("xbox", "xbox"),
    ("nintendo", "nintendo"),
    ("wii", "nintendo"),
    ("steam", "steam"),
    ("pc", "steam"),
)

SOURCE_SCORE_FIELDS: dict[str, str] = {
    "Steam": "steam_score",
    "OpenCritic": "opencritic_score",
    "Metacritic": "metacritic_live_score",
}

DERIVED_FIELDS = (
    "review_count_total",
    "live_review_count",
    "live_primary_sources",
    "has_live_critic",
    "steam_score",
    "opencritic_score",
    "metacritic_live_score",
    "platform_tags",
    "mode_tags",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _clean(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [v.strip().lower() for v in values if isinstance(v, str)]


def platform_tags(platforms: Any) -> list[str]:
    tags: set[str] = set()
    for name in _clean(platforms):
        if not name:
            continue
        tags.add(name)
        tags.update(tag for needle, tag in _PLATFORM_UMBRELLAS if needle in name)
    return sorted(tags)


def mode_tags(game_modes: Any, genres: Any) -> list[str]:
    tags = {m for m in _clean(game_modes) if m in PLAYER_MODE_GENRE_ALIASES}
    genre_values = set(_clean(genres))
    tags.update(key for key, aliases in PLAYER_MODE_GENRE_ALIASES.items() if genre_values & aliases)
    return sorted(tags)


def derive_catalog_columns(
    source_scores: Any,
    platforms: Any,
    game_modes: Any = None,
    genres: Any = None,
) -> dict[str, Any]:
    rows: Iterable[Mapping[str, Any]] = (
        [row for row in source_scores if isinstance(row, dict)] if isinstance(source_scores, list) else []
    )
    pc = any(name in PC_PLATFORM_KEYS for name in _clean(platforms))
    review_total = 0
    live_reviews = 0
    live_primary = 0
    has_critic = False
    best = {field: 0.0 for field in SOURCE_SCORE_FIELDS.values()}

    for row in rows:
        score = _number(row.get("score"))
        live = row.get("status") == "live" and score is not None and 0 < score <= MAX_VALID_SCORE
        reviews = _number(row.get("review_count"))
        count = int(reviews) if reviews is not None and 0 <= int(reviews) <= MAX_REVIEW_COUNT else 0
        review_total += count
        if not live:
            continue
        source = row.get("source")
        live_reviews += count
        if source in CRITIC_SOURCES:
            has_critic = True
        if source in PRIMARY_SOURCES and (source != "Steam" or pc):
            live_primary += 1
        field = SOURCE_SCORE_FIELDS.get(source) if isinstance(source, str) else None
        if field and score is not None:
            best[field] = max(best[field], score)

    return {
        "review_count_total": review_total,
        "live_review_count": live_reviews,
        "live_primary_sources": live_primary,
        "has_live_critic": has_critic,
        **best,
        "platform_tags": platform_tags(platforms),
        "mode_tags": mode_tags(game_modes, genres),
    }


_SOURCE_FIELDS = ("source_scores", "platforms", "game_modes", "genres")


def _inputs_changed(game: Any) -> bool:
    """True when any input attribute was assigned; avoids loading deferred columns."""
    from sqlalchemy import inspect

    state = inspect(game)
    return any(state.attrs[name].history.has_changes() for name in _SOURCE_FIELDS)


def apply_derived_columns(game: Any, *, only_if_changed: bool = False) -> None:
    """Write the derived columns onto a Game (or any object with the same attributes).

    With only_if_changed (the update hook) untouched rows are skipped, so partial
    loads (load_only/raiseload in background jobs) never trigger extra queries.
    """
    if only_if_changed and not _inputs_changed(game):
        return
    values = derive_catalog_columns(game.source_scores, game.platforms, game.game_modes, game.genres)
    for name, value in values.items():
        if getattr(game, name, None) != value:
            setattr(game, name, value)
