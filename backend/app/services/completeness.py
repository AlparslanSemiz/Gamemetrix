"""Data-completeness gate.

A game is "complete" once every axis we can fill has been filled or confirmed
unavailable, so the refresh rotation can skip it and spend API budget on the
incomplete tail instead. This is recomputed from live state — the persisted
`Game.data_complete` flag is only a cache of `compute_data_complete`.

Public API:
  compute_data_complete(game)  -> bool
  refresh_data_complete(game)  -> bool   (also writes game.data_complete)
  sweep_data_complete(db)      -> dict[str, int]
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from ..models import Game
from .metadata import looks_like_promo, summary_needs_enrichment
from .primary_score_backfill import missing_primary_score_sources

log = logging.getLogger(__name__)

_MISSING_COVER_VALUES = {"", "none", "null"}


def _has_cover(game: Game) -> bool:
    return bool(game.cover_url) and game.cover_url.strip().lower() not in _MISSING_COVER_VALUES


def _playtime_resolved(game: Game) -> bool:
    has_playtime = game.playtime_minutes > 0 or any((
        game.hltb_main_story_minutes,
        game.hltb_main_extra_minutes,
        game.hltb_completionist_minutes,
        game.hltb_all_styles_minutes,
    ))
    if has_playtime or game.is_endless:
        return True
    # HLTB and the endless classifier have both run and found nothing — accept
    # "unknown length" as resolved rather than retrying it forever.
    return game.hltb_refreshed_at is not None and game.endless_checked_at is not None


def compute_data_complete(game: Game) -> bool:
    if game.content_type != "game":
        return False
    if missing_primary_score_sources(game):
        return False
    if summary_needs_enrichment(game) or looks_like_promo(game.summary):
        return False
    if not _has_cover(game):
        return False
    if game.release_year <= 1970:
        return False
    return _playtime_resolved(game)


def refresh_data_complete(game: Game) -> bool:
    game.data_complete = compute_data_complete(game)
    return game.data_complete


def sweep_data_complete(db: Session) -> dict[str, int]:
    """Recompute the flag for the whole catalog. No API calls — pure state."""
    complete = 0
    changed = 0
    for game in db.scalars(
        select(Game).where(Game.content_type == "game").options(noload(Game.price_snapshots))
    ):
        before = game.data_complete
        if refresh_data_complete(game) != before:
            changed += 1
            db.add(game)
        if game.data_complete:
            complete += 1
    db.commit()
    return {"complete": complete, "changed": changed}
