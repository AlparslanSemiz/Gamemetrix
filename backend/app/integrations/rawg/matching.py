"""Deciding whether a RAWG result is really the game we asked about."""

from __future__ import annotations

import re

from ...models import Game

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_NUMERAL_TOKENS = {"ii": "2", "iii": "3", "iv": "4"}
_REMAKE_YEAR_TOLERANCE = 1


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = _NON_ALNUM_RE.sub(" ", value.lower()).strip()
    return " ".join(_NUMERAL_TOKENS.get(part, part) for part in normalized.split())


def title_matches(expected: str, candidate: str | None) -> bool:
    expected_norm = normalize_title(expected)
    candidate_norm = normalize_title(candidate)
    return bool(expected_norm and candidate_norm and expected_norm == candidate_norm)


def rawg_candidate_matches(game: Game, raw_game: dict) -> bool:
    if title_matches(game.title, raw_game.get("name")):
        return True
    return _remake_matches(game, raw_game)


def _remake_matches(game: Game, raw_game: dict) -> bool:
    expected_norm = normalize_title(game.title)
    if not expected_norm.endswith(" remake"):
        return False
    candidate_norm = normalize_title(raw_game.get("name"))
    if candidate_norm != expected_norm.removesuffix(" remake").strip():
        return False
    release_year = _released_year(raw_game)
    return release_year is not None and abs(release_year - game.release_year) <= _REMAKE_YEAR_TOLERANCE


def _released_year(raw_game: dict) -> int | None:
    released = str(raw_game.get("released") or "")
    return int(released[:4]) if released[:4].isdigit() else None


def rawg_game_url(raw_game: dict) -> str | None:
    slug = raw_game.get("slug")
    return f"https://rawg.io/games/{slug}" if slug else None
