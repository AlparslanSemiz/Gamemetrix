"""Title normalization for duplicate detection.

Reduces edition suffixes, year disambiguators, roman numerals and importer
qualifiers to a comparable key, so "DOOM (2016)", "DOOM" and "Doom: Definitive
Edition" collapse toward the same base.
"""

import re

_EDITION_SUFFIX_RE = re.compile(
    r"[\s:–—\-]+(?:"
    r"definitive(?: edition)?|royal(?: edition)?|remastered(?: edition)?|enhanced(?: edition)?|"
    r"complete(?: edition)?|goty(?: edition)?|game of the year(?: edition)?|"
    r"gold(?: edition)?|platinum(?: edition)?|legendary(?: edition)?|"
    r"ultimate(?: edition)?|deluxe(?: edition)?|director'?s cut|expanded(?: edition)?|"
    r"special(?: edition)?|collector'?s(?: edition)?|the final cut|final cut|"
    r"redux|hd(?: remaster)?|4k|the complete edition|landmark edition|komplete(?: edition)?|"
    r"anniversary edition"
    r")$",
    re.IGNORECASE,
)

# Stricter suffix regex used only for base_title (no "anniversary", no "gold" standalone)
_BASE_SUFFIX_RE = re.compile(
    r"[\s:–—\-]+(?:"
    r"definitive(?: edition)?|royal(?: edition)?|remastered(?: edition)?|enhanced(?: edition)?|"
    r"goty(?: edition)?|game of the year(?: edition)?|"
    r"gold edition|platinum(?: edition)?|"
    r"director'?s cut|"
    r"special(?: edition)?|collector'?s(?: edition)?|the final cut|final cut|"
    r"redux|hd(?: remaster)?|4k|landmark edition|komplete(?: edition)?|"
    r"anniversary edition"
    r")$",
    re.IGNORECASE,
)

# Strip parenthesized year disambiguators: "DOOM (2016)" → "DOOM", "Prey (2017)" → "Prey"
_YEAR_DISAMBIG_RE = re.compile(r"\s*\(\d{4}(?:[^)]*?)?\)\s*$")

# Strip parenthesized qualifiers added by importers: "(Classic)", "(2010 Edition)", etc.
_PAREN_QUALIFIER_RE = re.compile(
    r"\s*\((?:classic|retired|open beta|beta|playtest|\d{4}\s+edition)\)\s*$",
    re.IGNORECASE,
)

_ROMAN_TO_ARABIC = {
    "ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8",
    "ix": "9", "xi": "11", "xii": "12",
}
_ROMAN_RE = re.compile(r"\b(viii|vii|vi|iv|iii|ii|ix|xii|xi)\b", re.IGNORECASE)
_TRAILING_SLUG_INDEX_RE = re.compile(r"-\d{3,}$")


def _normalize_roman(value: str) -> str:
    return _ROMAN_RE.sub(lambda m: _ROMAN_TO_ARABIC.get(m.group().lower(), m.group()), value)


def normalized_title(value: str) -> str:
    value = value.replace("+", " plus ")
    value = _normalize_roman(value)
    return "".join(ch.casefold() for ch in value if ch.isalnum())


def canonical_title(value: str) -> str:
    stripped = _EDITION_SUFFIX_RE.sub("", value).strip()
    return normalized_title(stripped)


def base_title(value: str) -> str:
    """Remove year disambiguators, importer qualifiers and edition suffixes, then normalize."""
    t = _YEAR_DISAMBIG_RE.sub("", value).strip()
    t = _PAREN_QUALIFIER_RE.sub("", t).strip()
    t = _BASE_SUFFIX_RE.sub("", t).strip()
    return normalized_title(t)


def slug_key(slug: str) -> str:
    """Slug stem normalized like a title, so everquest-ii and everquest-2 compare equal."""
    stem = _TRAILING_SLUG_INDEX_RE.sub("", slug.lower())
    return normalized_title(stem)
