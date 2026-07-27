"""Backfill the four primary score sources for every catalog game."""

import asyncio
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import OPENCRITIC_SEARCH_SOURCE, get_settings
from ..database import SessionLocal
from ..integrations.rate_limiter import RateLimiter, get_rate_limiter
from ..integrations.source_registry import applicable_for_game
from ..integrations.sync import refresh_game_sources, score_value
from ..models import ExternalId, Game

PRIMARY_SCORE_SOURCES: tuple[str, ...] = ("OpenCritic", "Metacritic", "IGDB", "Steam")
PRIMARY_SCORE_TARGET_GAMES = 10_000
_SCAN_CHUNK = 500
_MIN_EXTERNAL_ID_CONFIDENCE = 0.8


def _has_live_score(game: Game, source: str) -> bool:
    return _has_live_score_values(game.source_scores, source)


def _has_live_score_values(source_scores: list[dict], source: str) -> bool:
    return any(
        row.get("source") == source
        and row.get("status") == "live"
        and score_value(row) is not None
        for row in source_scores
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


def _source_budget_available(
    limiter: RateLimiter,
    source: str,
    *,
    uses_local_metacritic: bool,
    has_opencritic_id: bool,
) -> bool:
    if uses_local_metacritic:
        return True
    if limiter.remaining(source) <= 0:
        return False
    return not (
        source == "OpenCritic"
        and not has_opencritic_id
        and limiter.remaining(OPENCRITIC_SEARCH_SOURCE) <= 0
    )


def _empty_source_rows() -> dict[str, dict[str, int | bool]]:
    return {
        source: {
            "live": 0,
            "missing": 0,
            "applicable": 0,
            "not_applicable": 0,
            "configured": _source_configured(source),
        }
        for source in PRIMARY_SCORE_SOURCES
    }


def _coverage_for_rows(rows) -> dict[str, object]:
    source_rows = _empty_source_rows()
    total = 0
    total_live_slots = 0
    total_missing_slots = 0
    complete_games = 0
    four_score_games = 0
    pc_games = 0
    score_count_distribution: Counter[int] = Counter()

    for platforms, source_scores in rows:
        total += 1
        applicable = applicable_for_game(
            [value for value in (platforms or []) if isinstance(value, str)]
        )
        if "Steam" in applicable:
            pc_games += 1
        live_sources = {
            source
            for source in PRIMARY_SCORE_SOURCES
            if _has_live_score_values(source_scores or [], source)
        }
        score_count_distribution[len(live_sources)] += 1
        if len(live_sources) == len(PRIMARY_SCORE_SOURCES):
            four_score_games += 1
        missing_count = 0
        for source in PRIMARY_SCORE_SOURCES:
            source_row = source_rows[source]
            if source not in applicable:
                source_row["not_applicable"] = int(source_row["not_applicable"]) + 1
                continue
            source_row["applicable"] = int(source_row["applicable"]) + 1
            if source in live_sources:
                source_row["live"] = int(source_row["live"]) + 1
                total_live_slots += 1
            else:
                source_row["missing"] = int(source_row["missing"]) + 1
                total_missing_slots += 1
                missing_count += 1
        if missing_count == 0:
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
        "four_score_games": four_score_games,
        "pc_games": pc_games,
        "non_pc_games": total - pc_games,
        "score_count_distribution": {
            str(score_count): score_count_distribution[score_count]
            for score_count in range(len(PRIMARY_SCORE_SOURCES) + 1)
        },
    }


def primary_score_coverage_status() -> dict[str, object]:
    # Stream plain column tuples instead of materialising 50k full Game ORM
    # objects (including every large metadata JSON field) in the API process.
    with SessionLocal() as db:
        catalog = _coverage_for_rows(
            db.execute(
                select(Game.platforms, Game.source_scores)
                .where(Game.content_type == "game")
                .execution_options(yield_per=_SCAN_CHUNK)
            )
        )
        top_target = _coverage_for_rows(
            db.execute(
                select(Game.platforms, Game.source_scores)
                .where(Game.content_type == "game")
                .order_by(
                    Game.rank_score.desc(),
                    Game.metrix_score.desc(),
                    Game.id.asc(),
                )
                .limit(PRIMARY_SCORE_TARGET_GAMES)
            )
        )
    catalog["top_target"] = {
        **top_target,
        "target_games": PRIMARY_SCORE_TARGET_GAMES,
    }
    return catalog


def primary_score_backfill_candidates(db: Session, limit: int, *, force: bool = False) -> list[tuple[int, tuple[str, ...]]]:
    scored: list[tuple[int, tuple[str, ...], float]] = []
    rows = db.execute(
        select(Game.id, Game.platforms, Game.source_scores, Game.rank_score)
        .where(Game.content_type == "game")
        .order_by(
            Game.rank_score.desc(),
            Game.metrix_score.desc(),
            Game.id.asc(),
        )
        .limit(PRIMARY_SCORE_TARGET_GAMES)
        .execution_options(yield_per=_SCAN_CHUNK)
    )
    for game_id, platforms, source_scores, rank_score in rows:
        applicable = applicable_for_game(
            [value for value in (platforms or []) if isinstance(value, str)]
        )
        missing = (
            tuple(source for source in PRIMARY_SCORE_SOURCES if source in applicable)
            if force
            else tuple(
                source
                for source in PRIMARY_SCORE_SOURCES
                if source in applicable
                and not _has_live_score_values(source_scores or [], source)
            )
        )
        if missing:
            scored.append((game_id, missing, rank_score))

    # The active KPI is the top 10k, so spend scarce daily calls there and finish
    # near-complete games first. This converts quota into completed four-score
    # records instead of spreading one extra score across the 52k catalog tail.
    scored.sort(key=lambda item: (len(item[1]), -item[2]))
    return [(game_id, missing) for game_id, missing, _ in scored[:limit]]


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
        candidate_ids = [game_id for game_id, _ in candidates]
        opencritic_game_ids: set[int] = set()
        if candidate_ids:
            opencritic_game_ids = set(
                db.scalars(
                    select(ExternalId.game_id).where(
                        ExternalId.game_id.in_(candidate_ids),
                        ExternalId.source == "OpenCritic",
                        ExternalId.is_primary.is_(True),
                        ExternalId.confidence >= _MIN_EXTERNAL_ID_CONFIDENCE,
                    )
                ).all()
            )

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
                if not _source_budget_available(
                    limiter,
                    source,
                    uses_local_metacritic=uses_local_metacritic,
                    has_opencritic_id=game.id in opencritic_game_ids,
                ):
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
