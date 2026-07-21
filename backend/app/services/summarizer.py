"""
AI-powered game summary maintenance.

Repairs promotional/dirty long descriptions and derives the short display blurb,
rotating through the whole catalog so every game is periodically re-checked.

Public API:
  needs_short_summary(game)         -> bool
  shorten_summary(title, summary)   -> Awaitable[str | None]
  rewrite_long_summary(title, text) -> Awaitable[str | None]
  shorten_summary_batch(db, limit)  -> Awaitable[dict[str, int]]
"""

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..integrations.groq import generate_text
from ..models import Game
from .metadata import looks_like_promo


log = logging.getLogger(__name__)

_MAX_SHORT_CHARS = 450
_MAX_LONG_CHARS = 700
_MIN_LONG_CHARS = 200   # only shorten if original is longer than this
_SYSTEM_PROMPT = (
    "You are a game description writer. "
    "Write a short paragraph of 3-4 sentences describing the given game. "
    "Capture the genre, core gameplay style, setting, and tone. "
    "Do NOT mention review scores, awards, prices, or platform names. "
    f"Stay strictly under {_MAX_SHORT_CHARS} characters. "
    "Write in English. Return only the description, no extra text."
)
_REWRITE_PROMPT = (
    "You are a game description writer. Rewrite the given text into a clean, "
    "factual 3-5 sentence description of the game. Remove all store, download, "
    "wishlist, price, and promotional language. Describe genre, core gameplay, "
    "setting, and tone. Do NOT invent facts that are not implied by the text. "
    f"Stay under {_MAX_LONG_CHARS} characters. Write in English. "
    "Return only the description, no extra text."
)

_WEAK_MARKERS: tuple[str, ...] = (
    "is part of the imported RAWG catalog",
    "is a Steam catalog entry",
    "is currently available via CheapShark",
    "Imported from FreeToGame",
    "was cached from RAWG search",
    "is a PC game with live store",
    "Steam audience data",
    "Critic and player scores are available",
)


def needs_short_summary(game: Game) -> bool:
    if game.summary_short:
        return False
    if len(game.summary) < _MIN_LONG_CHARS:
        return False
    return True


def _is_placeholder(summary: str) -> bool:
    return any(marker in summary for marker in _WEAK_MARKERS)


def _extract_sentences(text: str, max_chars: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    result = ""
    for sentence in sentences:
        candidate = (result + " " + sentence).strip() if result else sentence
        if len(candidate) > max_chars:
            break
        result = candidate
    return result or text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:") + "."


async def shorten_summary(title: str, summary: str) -> str | None:
    if _is_placeholder(summary):
        return None

    generated = await generate_text(
        _SYSTEM_PROMPT,
        f"Game: {title}\n\nDescription: {summary}",
    )
    if not generated:
        return _extract_sentences(summary, _MAX_SHORT_CHARS)
    if len(generated) > _MAX_SHORT_CHARS:
        return _extract_sentences(generated, _MAX_SHORT_CHARS)
    return generated


async def rewrite_long_summary(title: str, text: str) -> str | None:
    # Placeholder text carries no real content, so rewriting it would invent
    # facts — leave those to RAWG/IGDB enrichment instead.
    if _is_placeholder(text):
        return None
    generated = await generate_text(_REWRITE_PROMPT, f"Game: {title}\n\nText: {text}")
    if not generated:
        return None
    if len(generated) > _MAX_LONG_CHARS:
        generated = _extract_sentences(generated, _MAX_LONG_CHARS)
    return generated


async def shorten_summary_batch(db: Session, limit: int) -> dict[str, int]:
    # Oldest-checked first so the loop rotates through the whole catalog and
    # keeps re-visiting games as their long summaries improve.
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .order_by(Game.summary_refreshed_at.asc().nulls_first())
            .limit(limit * 2)
        ).all()
    )

    rewritten = 0
    shortened = 0
    skipped = 0
    processed = 0
    now = datetime.now(UTC)

    for game in games:
        if processed >= limit:
            break
        touched = False

        if looks_like_promo(game.summary) and not _is_placeholder(game.summary):
            new_long = await rewrite_long_summary(game.title, game.summary)
            if new_long:
                game.summary = new_long
                game.summary_short = None
                rewritten += 1
                touched = True

        if needs_short_summary(game):
            short = await shorten_summary(game.title, game.summary)
            if short:
                game.summary_short = short
                shortened += 1
                touched = True

        if not touched:
            skipped += 1
        game.summary_refreshed_at = now
        db.add(game)
        processed += 1

    db.commit()
    return {"rewritten": rewritten, "shortened": shortened, "skipped": skipped, "processed": processed}
