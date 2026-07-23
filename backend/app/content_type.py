"""Classifying a catalog entry as game / dlc / soundtrack / software / etc.

Title- and metadata-based heuristics only. Kept out of `models.py` (ORM only)
and below the services layer so integration importers can call it directly.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Game

SOFTWARE_GENRE_TERMS = {
    "animation",
    "audio production",
    "design",
    "education",
    "game development",
    "photo editing",
    "software",
    "video production",
    "web publishing",
}

KNOWN_CONTENT_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\baseprite\b", "software"),
    (r"\bwallpaper engine\b", "utility"),
    (r"\blossless scaling\b", "utility"),
    (r"\bsoundpad\b", "utility"),
    (r"\bvoicemod\b", "utility"),
    (r"\bvtube studio\b", "software"),
    (r"\bfacerig\b", "software"),
    (r"\bblender\b", "software"),
    (r"\bkrita\b", "software"),
    (r"\bclip studio paint\b", "software"),
    (r"\bsubstance\b", "software"),
    (r"\bmarmoset toolbag\b", "software"),
    (r"\brpg maker\b", "software"),
    (r"\bvisual novel maker\b", "software"),
    (r"\bgame maker\b", "software"),
    (r"\bgamemaker\b", "software"),
    (r"\bappgamekit\b", "software"),
    (r"\bclickteam fusion\b", "software"),
    (r"\bconstruct\b", "software"),
    (r"\bgodot\b", "software"),
    (r"\bunreal engine\b", "software"),
    (r"\bgameguru\b", "software"),
    (r"\bleadwerks\b", "software"),
    (r"\bspriter\b", "software"),
    (r"\bgame character hub\b", "software"),
    (r"\btilesetter\b", "software"),
)

_DLC_TITLE_RE = re.compile(
    r"""
    \b(?:
        dlc                             |
        downloadable\s+content          |
        season\s+pass                   |
        expansion\s+pass                |
        booster\s+pack                  |
        character\s+pack                |
        costume\s+pack                  |
        skin\s+pack                     |
        map\s+pack                      |
        weapon\s+pack                   |
        armor\s+pack                    |
        mission\s+pack                  |
        level\s+pack                    |
        adventure\s+pack                |
        content\s+pack                  |
        story\s+pack                    |
        add-?on\s+pack
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Title suffixes that indicate a sub-episode or DLC chapter
_EPISODE_SUFFIX_RE = re.compile(
    r"[\s\-–—]+(?:episode|chapter|part)\s+\d",
    re.IGNORECASE,
)

# The subtitle part (after " – " or " - ") must contain one of these keywords
# to be classified as a DLC via the parent-based heuristic.
# We deliberately require an explicit DLC-like keyword in the subtitle to avoid
# false-positives from games that just have a subtitle (e.g. "Eco - Global Survival Game").
_DLC_SUBTITLE_RE = re.compile(
    r"""
    \b(?:
        dlc                 |
        expansion           |
        add-?on             |
        episode\s+\d        |
        chapter\s+\d        |
        part\s+\d           |
        season\s+\d         |
        prelude             |
        prologue            |
        echoes              |     # Outer Wilds - Echoes of the Eye
        blood\s+dragon      |     # Far Cry 3 - Blood Dragon
        cindered\s+shadows  |     # Fire Emblem
        aiko.s\s+choice     |     # Shadow Tactics
        separate\s+ways     |     # RE4
        blood\s+and\s+wine  |     # Witcher 3
        hearts\s+of\s+stone |     # Witcher 3
        clone\s+carnage     |     # Destroy All Humans
        the\s+penal\s+zone  |     # Sam & Max
        iron\s+from\s+ice   |     # Game of Thrones
        zer0\s+sum          |     # Tales from the Borderlands
        toy\s+master        |     # Killing Floor
        wildfire            |     # Jagged Alliance 2
        rise\s+of\s+clans   |     # Hard Truck
        dark\s+crusade      |     # Dawn of War
        soulstorm           |     # Dawn of War
        winter\s+assault    |     # Dawn of War
        yuri.s\s+revenge    |     # C&C Red Alert 2
        uprising            |     # C&C Red Alert 3
        zero\s+hour               # C&C Generals
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# RAWG game_type values that indicate DLC/expansion
_RAWG_DLC_TYPES = frozenset({"dlc", "expansion", "addon", "update"})

_SUBTITLE_SEPARATORS = (" – ", " — ", " - ")


def infer_content_type(game: "Game", rawg_game_type: str | None = None) -> str:
    # RAWG explicitly tells us the type — trust it
    if rawg_game_type and rawg_game_type.lower() in _RAWG_DLC_TYPES:
        return "dlc"

    text = " ".join(
        [game.title, game.slug, *(game.genres or []), *(game.platforms or [])]
    ).lower()
    for pattern, content_type in KNOWN_CONTENT_TYPE_PATTERNS:
        if re.search(pattern, text):
            return content_type
    if "soundtrack" in text or re.search(r"\bost\b", text):
        return "soundtrack"
    if re.search(r"\b(demo|playtest)\b", text) or re.search(r"\bbeta\b", game.title, re.IGNORECASE):
        return "demo"
    if _DLC_TITLE_RE.search(game.title):
        return "dlc"
    if re.search(r"\b(dlc|downloadable content|season pass|expansion pass)\b", text):
        return "dlc"
    if _EPISODE_SUFFIX_RE.search(game.title):
        return "dlc"
    if re.search(r"\b(mod|sdk)\b", text):
        return "mod"
    if re.search(r"\b(utility|utilities|tool|tools)\b", text):
        return "utility"
    if any(term in text for term in SOFTWARE_GENRE_TERMS):
        return "software"
    return "game"


def infer_content_type_with_parent(game: "Game", parent_titles: frozenset[str]) -> str:
    """
    Extended classification that checks whether this game is a DLC/expansion of
    a parent game already in the catalog.

    Requires:
      1. Title matches "Parent Title – Subtitle" or "Parent Title - Subtitle"
      2. The parent title exists in the catalog
      3. The subtitle contains a recognized DLC/expansion keyword

    parent_titles: frozenset of all game titles currently in the DB (lowercase).
    """
    base_type = infer_content_type(game)
    if base_type != "game":
        return base_type

    title = game.title.strip()
    for separator in _SUBTITLE_SEPARATORS:
        if separator not in title:
            continue
        parent_candidate, _, subtitle = title.partition(separator)
        parent_candidate = parent_candidate.strip()
        subtitle = subtitle.strip()
        if not subtitle or not parent_candidate:
            continue
        if parent_candidate.lower() not in parent_titles:
            continue
        if _DLC_SUBTITLE_RE.search(subtitle):
            return "dlc"
    return "game"
