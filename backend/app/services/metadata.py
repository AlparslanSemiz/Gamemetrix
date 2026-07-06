"""
Summary and metadata helpers.

Public API:
  clean_game_summary(value, title) -> str | None
  summary_needs_enrichment(game)   -> bool
  enrich_game_summary(game)        -> Awaitable[None]
  fix_game_year(game)              -> Awaitable[bool]
"""

import html
import logging
import re
from datetime import date

from ..models import Game
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.rawg_score import get_rawg_game_metadata, get_rawg_release_date
from ..integrations.steam import extract_steam_app_id, get_steam_release_date


log = logging.getLogger(__name__)

# Summary quality thresholds
_MIN_SUMMARY_CHARS = 80       # shorter than this → not a real description
_MAX_SUMMARY_CHARS = 520      # hard cap before truncation
_TITLE_INJECT_MAX = 420       # only prepend title if summary is still short after truncation
_SENTENCES_TO_KEEP = 3        # max sentences to retain from the source text
_ENRICHMENT_MIN_CHARS = 120   # summaries below this length are considered weak
_RAWG_DESC_MIN_CHARS = 60     # minimum useful length for a RAWG description payload
_RAWG_DESC_MAX_CHARS = 3000   # cap stored description to avoid bloating the DB row

# Multi-byte UTF-8 sequences misread as Latin-1 (mojibake). Replace with correct characters.
_MOJIBAKE: dict[str, str] = {
    "â": "‘",  # left single quote
    "â": "’",  # right single quote
    "â": "“",  # left double quote
    "â": "”",  # right double quote
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
    for bad, good in _MOJIBAKE.items():
        normalized = normalized.replace(bad, good)
    if len(normalized) < _MIN_SUMMARY_CHARS:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    summary = " ".join(sentences[:_SENTENCES_TO_KEEP]).strip()
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[:_MAX_SUMMARY_CHARS].rsplit(" ", 1)[0].rstrip(".,;:") + "."
    if title.lower() not in summary.lower() and len(summary) < _TITLE_INJECT_MAX:
        summary = f"{title}: {summary}"

    return summary


def summary_needs_enrichment(game: Game) -> bool:
    if len(game.summary.strip()) < _ENRICHMENT_MIN_CHARS:
        return True
    return any(marker in game.summary for marker in _WEAK_SUMMARY_MARKERS)


async def enrich_game_summary(game: Game) -> None:
    if not summary_needs_enrichment(game):
        return
    try:
        if not await get_rate_limiter().acquire("RAWG"):
            return
        metadata = await get_rawg_game_metadata(game.title)
        if not metadata:
            return
        raw_desc = metadata.get("description_raw") or ""
        if len(raw_desc) < _RAWG_DESC_MIN_CHARS:
            raw_desc = re.sub(r"<[^>]+>", " ", metadata.get("description") or "")
            raw_desc = html.unescape(raw_desc).strip()
        if len(raw_desc) >= _RAWG_DESC_MIN_CHARS:
            game.summary = raw_desc[:_RAWG_DESC_MAX_CHARS].strip()
    except Exception:
        log.debug("Summary enrichment failed for %r", game.title, exc_info=True)


async def fix_game_year(game: Game) -> bool:
    if game.release_year and game.release_year != 1970:
        return False

    app_id = extract_steam_app_id(game.slug, game.cover_url)
    release_date: date | None = None
    if app_id and await get_rate_limiter().acquire("Steam"):
        release_date = await get_steam_release_date(app_id)
    if release_date is None:
        if not await get_rate_limiter().acquire("RAWG"):
            return False
        release_date = await get_rawg_release_date(game.title)

    if release_date is None or release_date.year <= 1970:
        return False

    game.release_date = release_date
    game.release_year = release_date.year
    return True
