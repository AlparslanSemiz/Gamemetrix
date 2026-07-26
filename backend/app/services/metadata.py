"""
Summary and metadata helpers.

Public API:
  clean_game_summary(value, title) -> str | None
  invalidate_summary_audit(game)   -> None
  summary_needs_enrichment(game)   -> bool
  enrich_game_summary(game)        -> Awaitable[None]
  fix_game_year(game)              -> Awaitable[bool]
  looks_like_placeholder(text)     -> bool
  looks_like_promo(text)           -> bool
  strip_markup(text)               -> str
  strip_promo(text)                -> str
  repair_mojibake(text)            -> str
"""

import html
import logging
import re
from datetime import UTC, date, datetime

from ..models import Game
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.rawg_score import get_rawg_game_metadata, get_rawg_release_date
from ..integrations.steam import extract_steam_app_id, get_steam_release_date


log = logging.getLogger(__name__)

# Verdict the description auditor stores on Game.summary_quality when the text
# holds nothing usable about the game. Defined here because metadata.py owns the
# "is this summary good enough" question; the summarizer package imports it.
UNUSABLE_SUMMARY_QUALITY = "unusable"

# Summary quality thresholds
_MIN_SUMMARY_CHARS = 80       # shorter than this → not a real description
_MAX_SUMMARY_CHARS = 520      # hard cap before truncation
_TITLE_INJECT_MAX = 420       # only prepend title if summary is still short after truncation
_SENTENCES_TO_KEEP = 3        # max sentences to retain from the source text
_ENRICHMENT_MIN_CHARS = 120   # summaries below this length are considered weak
_RAWG_DESC_MIN_CHARS = 60     # minimum useful length for a RAWG description payload
_RAWG_DESC_MAX_CHARS = 3000   # cap stored description to avoid bloating the DB row

# Multi-byte UTF-8 sequences misread as Latin-1 or CP1252 (mojibake). Replace
# with the correct characters. Longer keys must precede their prefixes, because
# the replacements are applied in order.
_MOJIBAKE: dict[str, str] = {
    "â": "‘",  # left single quote
    "â": "’",  # right single quote
    "â": "“",  # left double quote
    "â": "”",  # right double quote
    "â": "–",  # en dash
    "â": "—",  # em dash
    "â¦": "…",  # ellipsis
    # Same sequences after a CP1252 decode, where the punctuation byte renders
    # as a printable character instead of a control code. This is the form that
    # actually survives in stored provider text.
    "â€˜": "‘",
    "â€™": "’",
    "â€œ": "“",
    "â€“": "–",
    "â€”": "—",
    "â€¦": "…",
    "â€¢": "•",
    "â€": "”",        # keep last: closing quote leaves no trailing character
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã¤": "ä",
    "Ã¶": "ö",
    "Ã¼": "ü",
    "Ã¨": "è",
    "Ã§": "ç",
    "Ã‰": "É",
    "Ã–": "Ö",
    "Ãœ": "Ü",
    "Â®": "®",        # registered trademark
    "Â©": "©",        # copyright
    "Â": "",
}

# Sentences our own importers generate when a provider had no editorial text.
# Deliberately stored as the shortest distinctive fragment of each template so a
# reworded variant still matches. This is the single definition — summarizer and
# every other caller go through looks_like_placeholder().
_WEAK_SUMMARY_MARKERS: tuple[str, ...] = (
    "is a steam catalog entry",
    "is currently available via cheapshark",
    "imported from freetogame",
    "was cached from rawg search",
    "detailed editorial metadata can be enriched",
    "steam audience data",
    "is part of the imported rawg catalog",
    "is a pc game with live store",
    "it is available on pc through steam, with estimated ownership",
    "critic and player scores are available",
    "description unavailable",
    "no description available",
    "summary is not available",
)

# Storefront / marketing language that leaks into RAWG descriptions for indie and
# free games (e.g. "Here to download the game? Download Chapter 1 & 2…").
_PROMO_MARKERS: tuple[str, ...] = (
    "download the game",
    "download chapter",
    "\"download\"",
    "click the",
    "wishlist",
    "buy now",
    "on sale",
    "% off",
    "coming soon",
    "available now on",
    "pre-order",
    "pre order",
    "ダウンロード",
    "をクリック",
)


def strip_markup(text: str) -> str:
    """Drop HTML tags, decode entities and collapse whitespace."""
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def repair_mojibake(text: str) -> str:
    """Restore UTF-8 sequences that were decoded as Latin-1."""
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)
    return text


def looks_like_placeholder(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _WEAK_SUMMARY_MARKERS)


def looks_like_promo(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _PROMO_MARKERS)


def strip_promo(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if not looks_like_promo(s)]
    return " ".join(kept).strip() if kept else text


def clean_game_summary(value: str | None, title: str) -> str | None:
    if not value:
        return None

    normalized = repair_mojibake(strip_markup(value))
    if len(normalized) < _MIN_SUMMARY_CHARS:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    summary = " ".join(sentences[:_SENTENCES_TO_KEEP]).strip()
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[:_MAX_SUMMARY_CHARS].rsplit(" ", 1)[0].rstrip(".,;:") + "."
    if title.lower() not in summary.lower() and len(summary) < _TITLE_INJECT_MAX:
        summary = f"{title}: {summary}"

    return summary


def invalidate_summary_audit(game: Game) -> None:
    """Reset the description audit after the summary text was replaced.

    Call this from every writer of `Game.summary`. A verdict describes one
    specific text; leaving a stale `unusable` behind would keep the row
    permanently queued for provider re-enrichment.
    """
    game.summary_short = None
    game.summary_quality = None
    game.summary_checked_at = None


def summary_needs_enrichment(game: Game) -> bool:
    if len(game.summary.strip()) < _ENRICHMENT_MIN_CHARS:
        return True
    # Text the description auditor could not salvage carries no usable facts, so
    # only a fresh provider fetch can repair it.
    if game.summary_quality == UNUSABLE_SUMMARY_QUALITY:
        return True
    return looks_like_placeholder(game.summary)


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
        if len(raw_desc) < _RAWG_DESC_MIN_CHARS:
            return
        cleaned = clean_game_summary(strip_promo(raw_desc[:_RAWG_DESC_MAX_CHARS]), game.title)
        if cleaned:
            game.summary = cleaned
            invalidate_summary_audit(game)
            game.summary_refreshed_at = datetime.now(UTC)
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
