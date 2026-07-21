"""Endless (∞) playtime detection.

Some games have no fixed completion time — roguelikes, MMOs, sandbox, sports,
competitive multiplayer. HowLongToBeat has nothing for them, so without this
they read as "missing playtime" forever. Genre/mode heuristics decide the clear
cases; Groq classifies the ambiguous ones.

Public API:
  detect_endless(game)          -> bool | None   (None = ambiguous)
  classify_endless_ai(game)     -> Awaitable[bool | None]
  backfill_endless_batch(db, n) -> Awaitable[dict[str, int]]
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from ..config import get_settings
from ..integrations.groq import generate_text
from ..models import Game

log = logging.getLogger(__name__)

# Kept in sync with the frontend heuristic in utils/playtime.ts.
_ENDLESS_GENRES = {
    "roguelike", "roguelite", "rogue-like", "rogue-lite", "roguelikes", "rouge-like",
    "massively multiplayer", "mmo", "mmorpg", "battle royale",
    "sports", "racing", "sandbox", "party", "pinball",
}

_ENDLESS_PROMPT = (
    "You classify video games by whether they can be completed. Answer with "
    "exactly one word. ENDLESS if the game is built for indefinite, replayable "
    "play with no fixed ending (roguelikes, MMOs, sports, racing, sandbox, "
    "competitive multiplayer). FINITE if it has a story or campaign a player can "
    "finish. If unsure, answer FINITE."
)


def _genre_endless(game: Game) -> bool:
    return any((g or "").strip().lower() in _ENDLESS_GENRES for g in (game.genres or []))


def _has_completion_time(game: Game) -> bool:
    return any((
        game.hltb_main_story_minutes,
        game.hltb_main_extra_minutes,
        game.hltb_completionist_minutes,
        game.hltb_all_styles_minutes,
        game.playtime_minutes,
    ))


def _multiplayer_only(game: Game) -> bool:
    modes = [(m or "").lower() for m in (game.game_modes or [])]
    if not modes:
        return False
    has_single = any("single" in m for m in modes)
    has_multi = any(("multi" in m or "coop" in m or "co-op" in m or "battle" in m) for m in modes)
    return has_multi and not has_single


def detect_endless(game: Game) -> bool | None:
    """True endless, False has a completion, None ambiguous (needs AI)."""
    if _genre_endless(game):
        return True
    if _has_completion_time(game):
        return False
    if _multiplayer_only(game):
        return True
    return None


async def classify_endless_ai(game: Game) -> bool | None:
    genres = ", ".join(game.genres or []) or "unknown"
    modes = ", ".join(game.game_modes or []) or "unknown"
    answer = await generate_text(
        _ENDLESS_PROMPT,
        f"Game: {game.title}\nGenres: {genres}\nModes: {modes}",
    )
    if not answer:
        return None
    upper = answer.upper()
    if "ENDLESS" in upper:
        return True
    if "FINITE" in upper:
        return False
    return None


async def backfill_endless_batch(db: Session, limit: int) -> dict[str, int]:
    cfg = get_settings()
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .options(noload(Game.price_snapshots))
            .order_by(Game.endless_checked_at.asc().nulls_first())
            .limit(limit)
        ).all()
    )

    endless = 0
    finite = 0
    ai_used = 0
    now = datetime.now(UTC)

    for game in games:
        verdict = detect_endless(game)
        if verdict is None and cfg.ENDLESS_USE_AI and not _has_completion_time(game):
            verdict = await classify_endless_ai(game)
            ai_used += 1
        if verdict is not None and game.is_endless != verdict:
            game.is_endless = verdict
        game.endless_checked_at = now
        db.add(game)
        if game.is_endless:
            endless += 1
        else:
            finite += 1

    db.commit()
    return {"processed": len(games), "endless": endless, "finite": finite, "ai_used": ai_used}
