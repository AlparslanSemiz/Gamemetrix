"""Backfill the four primary score sources for every catalog game."""

import asyncio
from collections import Counter

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, noload

from ..config import get_settings
from ..database import SessionLocal
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.sync import _score_value, refresh_game_sources
from ..models import Game

PRIMARY_SCORE_SOURCES: tuple[str, ...] = ("OpenCritic", "Metacritic", "IGDB", "Steam")


def _has_live_score(game: Game, source: str) -> bool:
    return any(
        row.get("source") == source
        and row.get("status") == "live"
        and _score_value(row) is not None
        for row in game.source_scores
    )


def missing_primary_score_sources(game: Game) -> tuple[str, ...]:
    applicable = game.applicable_primary_sources
    return tuple(
        source
        for source in PRIMARY_SCORE_SOURCES
        if source in applicable and not _has_live_score(game, source)
    )


def _source_configured(source: str) -> bool:
    cfg = get_settings()
    if source == "Metacritic":
        return cfg.rawg_configured()
    if source == "OpenCritic":
        return cfg.opencritic_configured()
    if source == "IGDB":
        return cfg.igdb_configured()
    return True


def primary_score_coverage_status() -> dict[str, object]:
    with SessionLocal() as db:
        games = list(
            db.scalars(
                select(Game)
                .where(Game.content_type == "game")
                .options(noload(Game.price_snapshots))
            ).all()
        )

    total = len(games)
    source_rows: dict[str, dict[str, int | bool]] = {}
    total_live_slots = 0
    total_missing_slots = 0
    complete_games = 0

    for source in PRIMARY_SCORE_SOURCES:
        applicable = sum(1 for game in games if source in game.applicable_primary_sources)
        live = sum(
            1
            for game in games
            if source in game.applicable_primary_sources and _has_live_score(game, source)
        )
        missing = applicable - live
        total_live_slots += live
        total_missing_slots += missing
        source_rows[source] = {
            "live": live,
            "missing": missing,
            "applicable": applicable,
            "not_applicable": total - applicable,
            "configured": _source_configured(source),
        }

    for game in games:
        if not missing_primary_score_sources(game):
            complete_games += 1

    return {
        "sources": source_rows,
        "total_games": total,
        "complete_games": complete_games,
        "incomplete_games": total - complete_games,
        "live_score_slots": total_live_slots,
        "missing_score_slots": total_missing_slots,
        "target_score_slots": total_live_slots + total_missing_slots,
        "not_applicable_score_slots": total * len(PRIMARY_SCORE_SOURCES)
        - total_live_slots
        - total_missing_slots,
    }


def primary_score_backfill_candidates(db: Session, limit: int, *, force: bool = False) -> list[tuple[int, tuple[str, ...]]]:
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .options(noload(Game.price_snapshots))
            .order_by(desc(Game.rank_score), desc(Game.metrix_score), Game.title)
        ).all()
    )

    candidates: list[tuple[int, tuple[str, ...]]] = []
    for game in games:
        missing = (
            tuple(source for source in PRIMARY_SCORE_SOURCES if source in game.applicable_primary_sources)
            if force
            else missing_primary_score_sources(game)
        )
        if missing:
            candidates.append((game.id, tuple(missing)))
        if len(candidates) >= limit:
            break
    return candidates


async def primary_score_backfill_batch(
    limit: int = 10000,
    *,
    force: bool = False,
    inter_game_delay: float = 0.35,
) -> dict[str, object]:
    limiter = get_rate_limiter()
    attempted_games = refreshed_games = completed_games = skipped_games = failed_games = 0
    requested_slots = live_slots_added = 0
    skipped_by_reason: Counter[str] = Counter()
    attempted_by_source: Counter[str] = Counter()
    live_added_by_source: Counter[str] = Counter()

    with SessionLocal() as db:
        candidates = primary_score_backfill_candidates(db, limit, force=force)

    for game_id, planned_sources in candidates:
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None:
                skipped_games += 1
                continue
            configured_sources = []
            for source in planned_sources:
                uses_local_metacritic = source == "Metacritic" and game.metacritic_score is not None
                if not uses_local_metacritic and not _source_configured(source):
                    skipped_by_reason[f"{source}:not_configured"] += 1
                    continue
                if not uses_local_metacritic and limiter.remaining(source) <= 0:
                    skipped_by_reason[f"{source}:budget_exhausted"] += 1
                    continue
                configured_sources.append(source)

            if not configured_sources:
                skipped_games += 1
                continue

            if inter_game_delay > 0:
                await asyncio.sleep(inter_game_delay)

            attempted_games += 1
            requested_slots += len(configured_sources)
            attempted_by_source.update(configured_sources)
            before_live = {source for source in PRIMARY_SCORE_SOURCES if _has_live_score(game, source)}
            try:
                refreshed = await refresh_game_sources(
                    db,
                    game,
                    sources=configured_sources,
                    force=force,
                    include_support=False,
                    include_rawg_fallback=False,
                    refresh_metadata=False,
                )
            except Exception:
                failed_games += 1
                continue
            after_live = {source for source in PRIMARY_SCORE_SOURCES if _has_live_score(refreshed, source)}
            added = after_live - before_live
            if added:
                refreshed_games += 1
                live_slots_added += len(added)
                live_added_by_source.update(added)
            else:
                skipped_games += 1
            if len(after_live) == len(PRIMARY_SCORE_SOURCES):
                completed_games += 1

    return {
        "attempted_games": attempted_games,
        "refreshed_games": refreshed_games,
        "completed_games": completed_games,
        "skipped_games": skipped_games,
        "failed_games": failed_games,
        "requested_slots": requested_slots,
        "live_slots_added": live_slots_added,
        "attempted_by_source": dict(attempted_by_source),
        "live_added_by_source": dict(live_added_by_source),
        "skipped_by_reason": dict(skipped_by_reason),
        "coverage": primary_score_coverage_status(),
    }
