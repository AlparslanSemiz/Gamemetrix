"""Detect and remove entries that are not standalone playable games.

Bulk imports (SteamSpy "all" pages, RAWG catalog) let soundtracks, art books,
asset packs, tools, demos and dedicated servers into the catalog. `infer_content_type`
catches the obvious ones by title, but subtle cases (marker only in the summary,
generic-looking junk) slip through as `content_type == "game"`.

This is deliberately conservative:
  - Candidates are only the low-ranked games carrying a non-game signal.
  - Every candidate is confirmed by Groq — no AI, no action.
  - Permanent deletion needs a STRONG algorithmic marker AND AI agreement AND the
    autodelete flag AND no user having saved it. Everything else is quarantined
    (content_type flipped so it leaves public lists) — reversible, never destroyed.

Public API:
  nongame_cleanup_batch(db, limit) -> Awaitable[dict[str, int]]
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload

from ..config import get_settings
from ..integrations.groq import generate_text
from ..models import Game, UserCollection
from .admin_audit import record_admin_event

log = logging.getLogger(__name__)

# High-precision non-game phrases. Title OR summary — `infer_content_type` only
# reads the title/slug/genres/platforms, so a marker that appears solely in the
# summary is exactly what it misses.
_STRONG_NONGAME_MARKERS: tuple[str, ...] = (
    "soundtrack",
    "original soundtrack",
    " ost ",
    "art book",
    "artbook",
    "asset pack",
    "sound pack",
    "sfx pack",
    "wallpaper",
    "season pass",
    "expansion pass",
    "benchmark",
    "dedicated server",
)

_QUARANTINE_CONTENT_TYPE = "non-game"

_CLASSIFY_PROMPT = (
    "You decide whether a game-store entry is a standalone, playable video game "
    "or something else (soundtrack, art book, DLC/season pass, software/tool, "
    "asset pack, demo, or dedicated server). Reply with exactly one word: "
    "GAME or NOTGAME."
)


def _marker_text(game: Game) -> str:
    return f" {game.title} \n {game.summary} ".lower()


def _has_strong_marker(game: Game) -> bool:
    text = _marker_text(game)
    return any(marker in text for marker in _STRONG_NONGAME_MARKERS)


def _is_suspicious(game: Game) -> bool:
    if _has_strong_marker(game):
        return True
    # Thin junk: no genres and no developer is a strong shape for an asset/tool
    # entry that carries no real editorial data.
    return not (game.genres or []) and not game.developer


async def _ai_is_nongame(game: Game) -> bool | None:
    genres = ", ".join(game.genres or []) or "unknown"
    answer = await generate_text(
        _CLASSIFY_PROMPT,
        f"Title: {game.title}\nGenres: {genres}\nDescription: {game.summary[:600]}",
    )
    if not answer:
        return None
    upper = answer.upper()
    if "NOTGAME" in upper:
        return True
    if "GAME" in upper:
        return False
    return None


def _candidate_games(db: Session, limit: int) -> list[Game]:
    # Lowest-ranked first: junk clusters at the bottom of the catalog, which is
    # exactly where coverage complaints came from.
    out: list[Game] = []
    for game in db.scalars(
        select(Game)
        .where(Game.content_type == "game")
        .options(noload(Game.price_snapshots))
        .order_by(Game.rank_score.asc())
    ):
        if _is_suspicious(game):
            out.append(game)
        if len(out) >= limit:
            break
    return out


def _log_deletion(game: Game, reason: str) -> None:
    record_admin_event(
        username="system",
        action="nongame_delete",
        method="JOB",
        path=f"/games/{game.slug}",
        status_code=200,
        query=f"reason={reason}",
    )


async def nongame_cleanup_batch(db: Session, limit: int) -> dict[str, int]:
    cfg = get_settings()
    candidates = _candidate_games(db, limit)

    ai_checked = deleted = quarantined = kept = 0
    for game in candidates:
        strong = _has_strong_marker(game)
        verdict = await _ai_is_nongame(game)
        ai_checked += 1
        if verdict is not True:
            kept += 1
            continue

        referenced = db.scalar(
            select(func.count(UserCollection.id)).where(UserCollection.game_id == game.id)
        ) or 0

        if strong and cfg.NONGAME_AUTODELETE_ENABLED and referenced == 0:
            _log_deletion(game, "strong_marker+ai")
            db.delete(game)
            deleted += 1
        elif game.content_type != _QUARANTINE_CONTENT_TYPE:
            game.content_type = _QUARANTINE_CONTENT_TYPE
            db.add(game)
            quarantined += 1
        else:
            kept += 1

    db.commit()
    return {
        "candidates": len(candidates),
        "ai_checked": ai_checked,
        "deleted": deleted,
        "quarantined": quarantined,
        "kept": kept,
    }
