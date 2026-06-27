"""
Summary and metadata helpers.

Public API:
  clean_game_summary(value, title) -> str | None
  summary_needs_enrichment(game)   -> bool
  enrich_game_summary(game)        -> Awaitable[None]
  fix_game_year(game)              -> Awaitable[bool]
"""

import html
import re
from datetime import date

from ..models import Game
from ..integrations.rawg_score import get_rawg_game_metadata, get_rawg_release_date
from ..integrations.steam import extract_steam_app_id, get_steam_release_date


# Multi-byte UTF-8 sequences misread as Latin-1 — replace with correct characters.
_MOJIBAKE: dict[str, str] = {
    "â": "‘",  # left single quotation mark
    "â": "’",  # right single quotation mark
    "â": "“",  # left double quotation mark
    "â": "”",  # right double quotation mark
    "â": "–",  # en dash
    "â": "—",  # em dash
    "â¦": "…",  # ellipsis
    "Â®": "®",        # registered trademark
    "Â©": "©",        # copyright
    "Â": "",
}

_WEAK_SUMMARY_MARKERS: tuple[str, ...] = (
    "is a Steam catalog entry tracked by SteamSpy",
    "is currently available via CheapShark",
    "Imported from FreeToGame",
    "was cached from RAWG search",
    "Detailed editorial metadata can be enriched",
    "Steam audience data points to",
    "is part of the imported RAWG catalog",
    "is a PC game with live store and Steam audience data",
    "It is available on PC through Steam, with estimated ownership",
    "Critic and player scores are available from multiple sources",
)


def clean_game_summary(value: str | None, title: str) -> str | None:
    if not value:
        return None

    normalized = html.unescape(re.sub(r"\s+", " ", value)).strip()
    for bad, replacement in _MOJIBAKE.items():
        normalized = normalized.replace(bad, replacement)
    if len(normalized) < 80:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    summary = " ".join(sentences[:3]).strip()
    if len(summary) > 520:
        summary = summary[:520].rsplit(" ", 1)[0].rstrip(".,;:") + "."
    if title.lower() not in summary.lower() and len(summary) < 420:
        summary = f"{title}: {summary}"

    return summary


def summary_needs_enrichment(game: Game) -> bool:
    if len(game.summary.strip()) < 120:
        return True
    return any(marker in game.summary for marker in _WEAK_SUMMARY_MARKERS)


async def enrich_game_summary(game: Game) -> None:
    if not summary_needs_enrichment(game):
        return
    try:
        metadata = await get_rawg_game_metadata(game.title)
        if not metadata:
            return
        raw_desc = metadata.get("description_raw") or ""
        if len(raw_desc) < 60:
            raw_desc = re.sub(r"<[^>]+>", " ", metadata.get("description") or "")
            raw_desc = html.unescape(raw_desc).strip()
        if len(raw_desc) > 60:
            game.summary = raw_desc[:3000].strip()
    except Exception:
        pass


async def fix_game_year(game: Game) -> bool:
    if game.release_year and game.release_year != 1970:
        return False

    app_id = extract_steam_app_id(game.slug, game.cover_url)
    release_date: date | None = await get_steam_release_date(app_id) if app_id else None
    if release_date is None:
        release_date = await get_rawg_release_date(game.title)

    if release_date is None or release_date.year <= 1970:
        return False

    game.release_date = release_date
    game.release_year = release_date.year
    return True
