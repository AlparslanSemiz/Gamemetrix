"""What the catalog is still missing, plus the last run and live budgets."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, exists, func, select
from sqlalchemy.orm import Session

from ...database import SessionLocal
from ...heavy_jobs import HEAVY_JOB_LOCK
from ...integrations.rate_limiter import get_rate_limiter
from ...models import DataFillRun, ExternalId, Game, PriceSnapshot
from ..primary_score_backfill import primary_score_coverage_status
from .runs import serialize_run

PRICE_FRESHNESS = timedelta(hours=24)


def count_missing_external_ids() -> int:
    with SessionLocal() as db:
        has_external = exists(select(ExternalId.id).where(ExternalId.game_id == Game.id))
        return db.scalar(
            select(func.count(Game.id)).where(Game.content_type == "game", ~has_external)
        ) or 0


def _count_games(db: Session, *conditions) -> int:
    return db.scalar(
        select(func.count(Game.id)).where(Game.content_type == "game", *conditions)
    ) or 0


def data_fill_status() -> dict[str, object]:
    with SessionLocal() as db:
        total_games = _count_games(db)
        missing_ratings = _count_games(db, Game.ratings_refreshed_at.is_(None))
        missing_metadata = _count_games(db, Game.metadata_refreshed_at.is_(None))
        missing_hltb = _count_games(
            db,
            Game.hltb_id.is_(None),
            Game.playtime_minutes <= 0,
            Game.is_endless.is_(False),
        )
        has_fresh_price = exists(
            select(PriceSnapshot.id).where(
                PriceSnapshot.game_id == Game.id,
                PriceSnapshot.fetched_at >= datetime.now(UTC) - PRICE_FRESHNESS,
            )
        )
        missing_prices = _count_games(db, ~has_fresh_price)
        last_run = db.scalar(select(DataFillRun).order_by(desc(DataFillRun.started_at)).limit(1))
        last_run_payload = serialize_run(last_run)

    primary_scores = primary_score_coverage_status()
    return {
        "running": HEAVY_JOB_LOCK.locked(),
        "catalog": {
            "total_games": total_games,
            "missing_ratings": missing_ratings,
            "missing_primary_scores": primary_scores["missing_score_slots"],
            "primary_complete_games": primary_scores["complete_games"],
            "missing_metadata": missing_metadata,
            "missing_hltb": missing_hltb,
            "missing_prices": missing_prices,
            "missing_external_ids": count_missing_external_ids(),
        },
        "primary_scores": primary_scores,
        "rate_limits": get_rate_limiter().status(),
        "last_run": last_run_payload,
    }
