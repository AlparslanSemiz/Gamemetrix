"""
AI-powered game summary shortener.

Public API:
  needs_short_summary(game)         -> bool
  shorten_summary(title, summary)   -> Awaitable[str | None]
  shorten_summary_batch(db, limit)  -> Awaitable[dict[str, int]]
"""

import logging
import re

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..integrations.groq import generate_text
from ..models import Game


log = logging.getLogger(__name__)

_MAX_SHORT_CHARS = 450
_MIN_LONG_CHARS = 200   # only shorten if original is longer than this
_SYSTEM_PROMPT = (
    "You are a game description writer. "
    "Write a short paragraph of 3-4 sentences describing the given game. "
    "Capture the genre, core gameplay style, setting, and tone. "
    "Do NOT mention review scores, awards, prices, or platform names. "
    f"Stay strictly under {_MAX_SHORT_CHARS} characters. "
    "Write in English. Return only the description, no extra text."
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


async def shorten_summary_batch(db: Session, limit: int) -> dict[str, int]:
    games = list(
        db.scalars(
            select(Game)
            .where(Game.summary_short.is_(None))
            .where(Game.content_type == "game")
            .order_by(desc(Game.metrix_score))
            .limit(limit * 3)
        ).all()
    )

    shortened = 0
    skipped = 0

    for game in games:
        if shortened >= limit:
            break
        if not needs_short_summary(game):
            skipped += 1
            continue

        result = await shorten_summary(game.title, game.summary)
        if result:
            game.summary_short = result
            db.add(game)
            shortened += 1
        else:
            skipped += 1

    db.commit()
    return {"shortened": shortened, "skipped": skipped}
