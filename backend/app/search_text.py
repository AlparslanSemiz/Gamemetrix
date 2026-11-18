"""Search-text normalization shared by the Game model, the query builder and tests.

Leaf module. The SQL twin lives in the 0018 migration (backfill of existing rows):
unaccent + lower, delete apostrophes, every other non-alphanumeric run becomes one
space. Keep the two in step.
"""

import re
import unicodedata

_APOSTROPHES = "'’‘`´"
_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_MIN_FUZZY_LENGTH = 4


def normalize_search_text(value: str | None) -> str:
    """"Marvel's Spider-Man: Miles Morales" -> "marvels spider man miles morales"."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.casefold()
    for mark in _APOSTROPHES:
        lowered = lowered.replace(mark, "")
    return _NON_ALNUM_RE.sub(" ", lowered).strip()


def fuzzy_search_allowed(normalized_query: str) -> bool:
    """Trigram similarity on very short input matches almost everything."""
    return len(normalized_query) >= _MIN_FUZZY_LENGTH
