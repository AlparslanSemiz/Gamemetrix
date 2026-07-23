"""Deciding whether two games are the same title, and which copy is better.

`games_are_duplicates` layers three tests — exact normalized match, edition
variant, and disambiguator-stripped match — each with its own year tolerance.
"""

import re

from ...game_signals import safe_review_count
from ...models import Game
from .titles import base_title, canonical_title, normalized_title, slug_key

UNKNOWN_YEAR = 1970
_SAME_TITLE_YEAR_TOLERANCE = 4
_EDITION_YEAR_TOLERANCE = 10
_LONG_SUMMARY_CHARS = 120
_REMAKE_RE = re.compile(r"\bremake\b", re.IGNORECASE)
_TRAILING_INDEX_RE = re.compile(r"-\d+$")


def duplicate_key(game: Game) -> tuple[str, str, str]:
    return normalized_title(game.title), canonical_title(game.title), base_title(game.title)


def _years_match(left: int, right: int, tolerance: int) -> bool:
    if left == UNKNOWN_YEAR or right == UNKNOWN_YEAR:
        return True
    return abs(left - right) <= tolerance


def games_are_duplicates(left: Game, right: Game) -> bool:
    left_norm, left_canon, left_base = duplicate_key(left)
    right_norm, right_canon, right_base = duplicate_key(right)

    # 1. Exact normalized match (roman numerals already converted)
    if left_norm and left_norm == right_norm:
        return _exact_match_is_duplicate(left, right)

    # 2. Edition variant of same game (GOTY / Remastered / Definitive Edition …)
    if left_canon and left_canon == right_canon:
        verdict = _edition_variant_verdict(left, right, left_norm, right_norm, left_canon, right_canon)
        if verdict is not None:
            return verdict

    # 3. Year-disambiguated / paren-qualifier / edition-stripped titles:
    #    "DOOM (2016)" ↔ "DOOM", "Prey (2017)" ↔ "Prey",
    #    "Shadow Warrior (Classic)" ↔ "Shadow Warrior",
    #    "Mafia II (Classic)" ↔ "Mafia II: Definitive Edition"
    if left_base and left_base == right_base and (left_base != left_norm or left_base != right_norm):
        return _years_match(left.release_year, right.release_year, _EDITION_YEAR_TOLERANCE)
    return False


def _exact_match_is_duplicate(left: Game, right: Game) -> bool:
    if left.title.strip().casefold() == right.title.strip().casefold():
        return True
    if slug_key(left.slug) == slug_key(right.slug):
        return True
    return _years_match(left.release_year, right.release_year, _SAME_TITLE_YEAR_TOLERANCE)


def _edition_variant_verdict(
    left: Game,
    right: Game,
    left_norm: str,
    right_norm: str,
    left_canon: str,
    right_canon: str,
) -> bool | None:
    """True/False if the edition path is decisive, None to fall through to the base-title test."""
    # Guard: "Remake" is a distinct product, so an original and its remake with the
    # same canonical title must not merge via the edition path.
    if bool(_REMAKE_RE.search(left.title)) != bool(_REMAKE_RE.search(right.title)):
        return None
    if left_canon != left_norm or right_canon != right_norm:
        return _years_match(left.release_year, right.release_year, _EDITION_YEAR_TOLERANCE)
    return None


def total_review_count(game: Game) -> int:
    return sum(safe_review_count(s) for s in game.source_scores or [])


def duplicate_quality_key(game: Game) -> tuple[int, int, int, int, int, float, int]:
    slug_looks_curated = not _TRAILING_INDEX_RE.search(game.slug)
    metadata_score = sum([
        1 if game.release_year != UNKNOWN_YEAR else 0,
        1 if game.developer else 0,
        1 if game.publisher else 0,
        1 if game.summary and len(game.summary) > _LONG_SUMMARY_CHARS else 0,
        1 if game.cover_url else 0,
        1 if game.screenshots else 0,
    ])
    return (
        1 if slug_looks_curated else 0,
        1 if game.release_year != UNKNOWN_YEAR else 0,
        metadata_score,
        game.live_primary_source_count,
        total_review_count(game),
        game.rank_score or game.metrix_score,
        -(game.id or 0),
    )
