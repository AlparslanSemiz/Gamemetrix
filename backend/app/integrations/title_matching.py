from __future__ import annotations

import re
from difflib import SequenceMatcher


_ROMAN_NUMERALS = {"ii": "2", "iii": "3", "iv": "4", "v": "5"}
_EDITION_SUFFIXES = (
    " game of the year edition",
    " goty edition",
    " ultimate edition",
    " complete edition",
    " definitive edition",
    " deluxe edition",
    " standard edition",
)


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    parts = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    return " ".join(_ROMAN_NUMERALS.get(part, part) for part in parts)


def _without_edition(value: str) -> str:
    for suffix in _EDITION_SUFFIXES:
        if value.endswith(suffix):
            return value.removesuffix(suffix).strip()
    return value


def title_match_quality(
    expected: str,
    candidate: str | None,
    *,
    expected_year: int | None = None,
    candidate_year: int | None = None,
) -> float:
    expected_norm = normalize_title(expected)
    candidate_norm = normalize_title(candidate)
    if not expected_norm or not candidate_norm:
        return 0.0
    if expected_year and candidate_year and abs(expected_year - candidate_year) > 2:
        return 0.0

    expected_numbers = {part for part in expected_norm.split() if part.isdigit()}
    candidate_numbers = {part for part in candidate_norm.split() if part.isdigit()}
    if expected_numbers != candidate_numbers:
        return 0.0

    if expected_norm == candidate_norm:
        return 1.0
    if _without_edition(expected_norm) == _without_edition(candidate_norm):
        return 0.99

    shorter, longer = sorted((expected_norm, candidate_norm), key=len)
    if shorter in longer and len(shorter) / len(longer) >= 0.7:
        return 0.95
    ratio = SequenceMatcher(None, expected_norm, candidate_norm).ratio()
    return ratio if ratio >= 0.9 else 0.0


def titles_match(
    expected: str,
    candidate: str | None,
    *,
    expected_year: int | None = None,
    candidate_year: int | None = None,
) -> bool:
    return title_match_quality(
        expected,
        candidate,
        expected_year=expected_year,
        candidate_year=candidate_year,
    ) > 0
