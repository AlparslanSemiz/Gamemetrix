"""Fill top-catalog IGDB scores in batches of 500 known external IDs."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..integrations.igdb_scores import MAX_IGDB_SCORE_BATCH, get_igdb_scores
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.types import ExternalScore
from ..integrations.sync import (
    calculate_metrix_score,
    merge_source_scores,
    persist_source_records,
    update_derived_scores,
)
from ..models import ExternalId, Game, SourceSnapshot
from .primary_score_backfill import (
    PRIMARY_SCORE_TARGET_GAMES,
    _has_live_score_values,
)

log = logging.getLogger(__name__)

_SNAPSHOT_ENDPOINT = "rating-backfill/igdb-bulk"
_RETRY_AFTER = timedelta(days=30)


def _candidates(db: Session, limit: int, *, force: bool = False) -> list[tuple[int, int]]:
    retry_cutoff = datetime.now(UTC) - _RETRY_AFTER
    checked_recently = exists(
        select(SourceSnapshot.id).where(
            SourceSnapshot.source == "IGDB",
            SourceSnapshot.endpoint == _SNAPSHOT_ENDPOINT,
            SourceSnapshot.external_id == ExternalId.external_id,
            SourceSnapshot.fetched_at >= retry_cutoff,
        )
    )
    conditions = [Game.content_type == "game"]
    if not force:
        conditions.append(~checked_recently)
    top_games = (
        select(Game.id)
        .where(Game.content_type == "game")
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc(), Game.id.asc())
        .limit(PRIMARY_SCORE_TARGET_GAMES)
        .subquery()
    )
    rows = db.execute(
        select(Game.id, ExternalId.external_id, Game.source_scores)
        .join(top_games, top_games.c.id == Game.id)
        .join(
            ExternalId,
            and_(ExternalId.game_id == Game.id, ExternalId.source == "IGDB"),
        )
        .where(*conditions)
        .order_by(Game.rank_score.desc(), Game.metrix_score.desc(), Game.id.asc())
    )
    candidates: list[tuple[int, int]] = []
    seen_game_ids: set[int] = set()
    for game_id, external_id, source_scores in rows:
        if game_id in seen_game_ids:
            continue
        if not force and _has_live_score_values(source_scores or [], "IGDB"):
            continue
        if external_id and str(external_id).isdigit():
            candidates.append((int(game_id), int(external_id)))
            seen_game_ids.add(int(game_id))
        if len(candidates) >= limit:
            break
    return candidates


def _chunks(candidates: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    return [
        candidates[index:index + MAX_IGDB_SCORE_BATCH]
        for index in range(0, len(candidates), MAX_IGDB_SCORE_BATCH)
    ]


def _store_batch(
    candidates: list[tuple[int, int]],
    scores: dict[int, ExternalScore],
) -> tuple[int, int]:
    from .completeness import refresh_data_complete
    from .seo import refresh_game_seo_state

    now = datetime.now(UTC)
    filled = unavailable = 0
    with SessionLocal() as db:
        for game_id, igdb_id in candidates:
            game = db.get(Game, game_id)
            score = scores.get(igdb_id)
            if game is not None and score is not None:
                had_score = _has_live_score_values(game.source_scores or [], "IGDB")
                game.source_scores = merge_source_scores(game.source_scores, [score])
                game.metrix_score = calculate_metrix_score(game.source_scores)
                game.ratings_refreshed_at = now
                update_derived_scores(game, [score])
                persist_source_records(db, game, [score])
                refresh_game_seo_state(game, content_updated=True)
                refresh_data_complete(game)
                db.add(game)
                if not had_score:
                    filled += 1
            else:
                unavailable += 1
            db.add(
                SourceSnapshot(
                    source="IGDB",
                    endpoint=_SNAPSHOT_ENDPOINT,
                    query=None,
                    external_id=str(igdb_id),
                    status_code=200,
                    raw_payload={"rating_found": score is not None},
                    fetched_at=now,
                    created_at=now,
                )
            )
        db.commit()
    return filled, unavailable


async def igdb_score_backfill_batch(
    limit: int = PRIMARY_SCORE_TARGET_GAMES,
    *,
    force: bool = False,
    inter_batch_delay: float = 0.35,
) -> dict[str, int]:
    with SessionLocal() as db:
        candidates = _candidates(db, limit, force=force)

    considered = filled = unavailable = failed = 0
    for batch in _chunks(candidates):
        limiter = get_rate_limiter()
        if limiter.remaining("IGDB") <= 0 or not await limiter.acquire("IGDB"):
            break
        if inter_batch_delay > 0:
            await asyncio.sleep(inter_batch_delay)
        scores = await get_igdb_scores([igdb_id for _, igdb_id in batch])
        if scores is None:
            failed += len(batch)
            continue
        considered += len(batch)
        batch_filled, batch_unavailable = _store_batch(batch, scores)
        filled += batch_filled
        unavailable += batch_unavailable
    return {
        "considered": considered,
        "filled": filled,
        "unavailable": unavailable,
        "failed": failed,
    }
