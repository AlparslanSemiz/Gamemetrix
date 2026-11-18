"""Does a Steam app actually describe this catalog game?

An app id is only trusted after its appdetails block agrees with the row: the
product type is `game`, the name matches, and a year/"(Retired)" qualifier on
either side does not point at a different product. Pure functions over plain
values, so importers, backfills and the audit command share one rule.
"""

import re
from dataclasses import dataclass
from datetime import date

from ..title_matching import normalize_title, title_match_quality

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
# A qualifier naming one of these is a different product from the unqualified title.
_DISTINCT_QUALIFIERS = frozenset({"retired", "open beta", "beta", "playtest", "demo", "legacy"})
# Remasters and ports legitimately carry a different year than the original row.
_REMAKE_RE = re.compile(
    r"\b(remaster(?:ed)?|remake|definitive|hd|anniversary|enhanced|redux|reloaded)\b",
    re.IGNORECASE,
)
_NON_GAME_TYPES = frozenset({"dlc", "music", "demo", "mod", "advertising", "hardware", "video", "series"})


@dataclass(frozen=True)
class SteamIdentity:
    ok: bool
    reason: str
    name_matches: bool = False
    steam_type: str | None = None


def split_qualifiers(title: str) -> tuple[str, frozenset[str]]:
    """Title without parenthesised qualifiers, plus the distinguishing ones."""
    found: set[str] = set()
    for raw in _PAREN_RE.findall(title or ""):
        token = normalize_title(raw)
        if _YEAR_RE.match(token) or token in _DISTINCT_QUALIFIERS:
            found.add(token)
    stripped = _PAREN_RE.sub(" ", title or "")
    return stripped.strip(), frozenset(found)


def _qualifiers_conflict(
    ours: frozenset[str],
    theirs: frozenset[str],
    our_year: int | None,
    their_year: int | None,
) -> bool:
    # A bare year qualifier that equals the other side's release year is just a
    # disambiguator for the same product ("Modern Warfare 2" vs "... 2 (2009)").
    left = {q for q in ours if not (_YEAR_RE.match(q) and their_year and int(q) == their_year)}
    right = {q for q in theirs if not (_YEAR_RE.match(q) and our_year and int(q) == our_year)}
    return left != right


def steam_identity_verdict(
    title: str,
    release_year: int | None,
    *,
    steam_name: str | None,
    steam_year: int | None = None,
    steam_type: str | None = None,
) -> SteamIdentity:
    """Judge one appdetails block against a catalog row."""
    year = release_year if release_year and release_year > 1970 else None
    our_title, our_quals = split_qualifiers(title)
    their_title, their_quals = split_qualifiers(steam_name or "")
    if not normalize_title(their_title):
        return SteamIdentity(False, "empty_name", steam_type=steam_type)

    tolerant = bool(_REMAKE_RE.search(title) or _REMAKE_RE.search(steam_name or ""))
    quality = title_match_quality(
        our_title,
        their_title,
        expected_year=None if tolerant else year,
        candidate_year=None if tolerant else steam_year,
    )
    name_matches = quality > 0
    if name_matches and _qualifiers_conflict(our_quals, their_quals, year, steam_year):
        return SteamIdentity(False, "qualifier_mismatch", name_matches=False, steam_type=steam_type)
    if not name_matches:
        return SteamIdentity(False, "name_mismatch", steam_type=steam_type)
    kind = (steam_type or "game").lower()
    if kind != "game":
        return SteamIdentity(False, f"type:{kind}", name_matches=True, steam_type=kind)
    return SteamIdentity(True, "ok", name_matches=True, steam_type=kind)


def steam_title_plausible(title: str, steam_name: str | None) -> bool:
    """Cheap name-only gate for store-search hits, before any appdetails call."""
    our_title, our_quals = split_qualifiers(title)
    their_title, their_quals = split_qualifiers(steam_name or "")
    non_year = lambda quals: {q for q in quals if not _YEAR_RE.match(q)}  # noqa: E731
    if non_year(our_quals) != non_year(their_quals):
        return False
    return title_match_quality(our_title, their_title) > 0


def appdetails_product_type(data: dict) -> str:
    """`game`, `dlc`, `music`, ... — an app with a `fullgame` parent is a DLC whatever it claims."""
    kind = str(data.get("type") or "game").lower()
    if data.get("fullgame") and kind == "game":
        return "dlc"
    return kind


def identity_from_appdetails(
    title: str,
    release_year: int | None,
    data: dict | None,
    steam_release: date | None = None,
) -> SteamIdentity:
    """Verdict straight from a raw appdetails `data` block (None = no usable data)."""
    if not data:
        return SteamIdentity(False, "no_appdetails")
    kind = appdetails_product_type(data)
    return steam_identity_verdict(
        title,
        release_year,
        steam_name=str(data.get("name") or ""),
        steam_year=steam_release.year if steam_release else None,
        steam_type=kind,
    )


def is_non_game_steam_type(steam_type: str | None) -> bool:
    return (steam_type or "game").lower() in _NON_GAME_TYPES
