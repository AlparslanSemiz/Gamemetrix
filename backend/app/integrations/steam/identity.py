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
_APOSTROPHES = re.compile(r"[\u2019\u2018\u02bc'`\u00b4]")
_MARKS = re.compile(r"[\u2122\u00ae\u00a9]")
_BRAND_PREFIXES = ("sid meiers ", "tom clancys ")
# Release-edition tails that do not make a different product ("... Remastered").
_EDITION_TAIL_RE = re.compile(
    r"(?: (?:the )?(?:game of the year|goty|[a-z]+) edition| remastered| remaster| goty| directors cut)$"
)
_REMAKE_TAIL = " remake"
# A Steam release this many years after the catalog year is still a late PC port.
_MAX_PORT_LAG_YEARS = 6
_YEAR_TOLERANCE = 2
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


def canonical_title(title: str) -> tuple[str, bool]:
    """Comparison form of a title, and whether an edition tail was dropped.

    Drops marks, apostrophes, brand prefixes ("Sid Meier's") and release-edition
    tails; punctuation, dashes and case vanish in `normalize_title`.
    """
    text = _APOSTROPHES.sub("", _MARKS.sub("", title or "")).replace("&amp;", "&")
    norm = normalize_title(text)
    for prefix in _BRAND_PREFIXES:
        if norm.startswith(prefix):
            norm = norm.removeprefix(prefix)
    stripped = False
    while True:
        shorter = _EDITION_TAIL_RE.sub("", norm)
        if shorter == norm or not shorter:
            return norm, stripped
        norm, stripped = shorter, True


def _qualifiers_conflict(ours: frozenset[str], theirs: frozenset[str]) -> bool:
    """Non-year qualifiers ("Retired", "Playtest") must agree; years are judged separately."""
    return {q for q in ours if not _YEAR_RE.match(q)} != {q for q in theirs if not _YEAR_RE.match(q)}


def _qualifier_year(quals: frozenset[str]) -> int | None:
    years = sorted(int(q) for q in quals if _YEAR_RE.match(q))
    return years[0] if years else None


def _year_conflict(
    our_year: int | None,
    steam_year: int | None,
    steam_explicit_year: int | None,
) -> bool:
    """Same name, but the years say a different product.

    An explicit year in the Steam name ("Modern Warfare 2 (2009)") must sit near ours.
    Otherwise Steam's release date may trail the catalog year by a few years (late PC
    port) or precede it (early access); a far-later release is a different game.
    """
    if not our_year:
        return False
    if steam_explicit_year:
        return abs(steam_explicit_year - our_year) > _YEAR_TOLERANCE
    if steam_year and steam_year - our_year > _MAX_PORT_LAG_YEARS:
        return True
    return False


def steam_identity_verdict(
    title: str,
    release_year: int | None,
    *,
    steam_name: str | None,
    steam_year: int | None = None,
    steam_type: str | None = None,
) -> SteamIdentity:
    """Judge one appdetails block against a catalog row."""
    our_title, our_quals = split_qualifiers(title)
    their_title, their_quals = split_qualifiers(steam_name or "")
    if not normalize_title(their_title):
        return SteamIdentity(False, "empty_name", steam_type=steam_type)
    # An explicit "(2018)" on our title is the original year and beats the row's.
    year = _qualifier_year(our_quals) or (release_year if release_year and release_year > 1970 else None)

    ours, our_cut = canonical_title(our_title)
    theirs, their_cut = canonical_title(their_title)
    remake = False
    if ours != theirs:
        for left, right in ((ours, theirs), (theirs, ours)):
            if left.endswith(_REMAKE_TAIL) and left.removesuffix(_REMAKE_TAIL) == right:
                remake = True
        if remake and year and steam_year and abs(steam_year - year) > _YEAR_TOLERANCE:
            return SteamIdentity(False, "year_mismatch", steam_type=steam_type)
    name_matches = (ours == theirs or remake) or title_match_quality(ours, theirs) > 0
    if not name_matches:
        return SteamIdentity(False, "name_mismatch", steam_type=steam_type)
    if _qualifiers_conflict(our_quals, their_quals):
        return SteamIdentity(False, "qualifier_mismatch", steam_type=steam_type)
    reissue = our_cut or their_cut or remake or bool(_REMAKE_RE.search(title) or _REMAKE_RE.search(steam_name or ""))
    if not reissue and _year_conflict(year, steam_year, _qualifier_year(their_quals)):
        return SteamIdentity(False, "year_mismatch", name_matches=True, steam_type=steam_type)
    kind = (steam_type or "game").lower()
    if kind != "game":
        return SteamIdentity(False, "not_game", name_matches=True, steam_type=kind)
    return SteamIdentity(True, "ok", name_matches=True, steam_type=kind)


def steam_title_plausible(title: str, steam_name: str | None) -> bool:
    """Cheap name-only gate for store-search hits, before any appdetails call."""
    our_title, our_quals = split_qualifiers(title)
    their_title, their_quals = split_qualifiers(steam_name or "")
    if _qualifiers_conflict(our_quals, their_quals):
        return False
    ours, _ = canonical_title(our_title)
    theirs, _ = canonical_title(their_title)
    return ours == theirs or title_match_quality(ours, theirs) > 0


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
