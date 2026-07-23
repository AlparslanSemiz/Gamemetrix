"""Scoring HowLongToBeat search rows against the title we asked for."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

MIN_MATCH_SIMILARITY = 0.72
_MISSING_NUMBER_PENALTY = 0.1
_YEAR_MATCH_BONUS = 0.06
_HAS_PLAYTIME_BONUS = 0.03
_YEAR_TOLERANCE = 1
_SECONDS_PER_MINUTE = 60

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class HltbMatch:
    hltb_id: int
    title: str
    url: str
    image_url: str | None
    similarity: float
    release_year: int | None
    main_story_minutes: int
    main_extra_minutes: int
    completionist_minutes: int
    all_styles_minutes: int
    raw: dict[str, Any]


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


def similarity(expected: str, candidate: str | None) -> float:
    expected_norm = normalize_title(expected)
    candidate_norm = normalize_title(candidate)
    if not expected_norm or not candidate_norm:
        return 0.0

    score = SequenceMatcher(None, expected_norm, candidate_norm).ratio()
    expected_numbers = {part for part in expected_norm.split() if part.isdigit()}
    candidate_numbers = {part for part in candidate_norm.split() if part.isdigit()}
    if expected_numbers and not expected_numbers <= candidate_numbers:
        score -= _MISSING_NUMBER_PENALTY
    return max(0.0, score)


def seconds_to_minutes(value: Any) -> int:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(1, round(seconds / _SECONDS_PER_MINUTE))


def best_playtime_minutes(match: HltbMatch) -> int:
    return (
        match.main_story_minutes
        or match.all_styles_minutes
        or match.main_extra_minutes
        or match.completionist_minutes
        or 0
    )


def best_match(
    title: str,
    release_year: int | None,
    rows: list[dict[str, Any]],
    *,
    game_url: str,
    image_url_prefix: str,
) -> HltbMatch | None:
    ranked: list[tuple[float, HltbMatch]] = []
    for row in rows:
        match = _row_to_match(title, row, game_url=game_url, image_url_prefix=image_url_prefix)
        if match is None or match.similarity < MIN_MATCH_SIMILARITY:
            continue
        ranked.append((_rank(match, release_year), match))
    if not ranked:
        return None
    return max(ranked, key=lambda item: item[0])[1]


def _row_to_match(
    title: str,
    row: dict[str, Any],
    *,
    game_url: str,
    image_url_prefix: str,
) -> HltbMatch | None:
    if str(row.get("game_type") or "game").lower() not in {"game", ""}:
        return None
    hltb_id = row.get("game_id")
    if not hltb_id:
        return None

    image = row.get("game_image")
    return HltbMatch(
        hltb_id=int(hltb_id),
        title=str(row.get("game_name") or title),
        url=f"{game_url}/{hltb_id}",
        image_url=f"{image_url_prefix}{image}" if isinstance(image, str) and image else None,
        similarity=round(
            max(similarity(title, row.get("game_name")), similarity(title, row.get("game_alias"))),
            3,
        ),
        release_year=_release_year(row.get("release_world")),
        main_story_minutes=seconds_to_minutes(row.get("comp_main")),
        main_extra_minutes=seconds_to_minutes(row.get("comp_plus")),
        completionist_minutes=seconds_to_minutes(row.get("comp_100")),
        all_styles_minutes=seconds_to_minutes(row.get("comp_all")),
        raw=row,
    )


def _release_year(value: Any) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _rank(match: HltbMatch, release_year: int | None) -> float:
    rank = match.similarity
    if release_year and match.release_year and abs(release_year - match.release_year) <= _YEAR_TOLERANCE:
        rank += _YEAR_MATCH_BONUS
    if best_playtime_minutes(match) > 0:
        rank += _HAS_PLAYTIME_BONUS
    return rank
