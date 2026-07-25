"""Research and safely replace fields previously marked as bad metadata."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload

from ...config import get_settings
from ...models import CatalogQualityReview, Game
from ..admin_audit import record_admin_event
from ..metadata_backfill.persistence import store_source_snapshot, upsert_external_id
from ..seo import refresh_game_seo_state
from .remediation import (
    RepairPlan,
    ResearchedGame,
    apply_repair_plan,
    build_repair_plan,
    repair_fields,
    restore_repair,
)
from .research import research_game
from .review import ai_review

log = logging.getLogger(__name__)

_SEARCH_CONFIDENCE = 0.9
_TRUSTED_CONFIDENCE = 0.97


async def catalog_repair_batch(db: Session, limit: int) -> dict[str, int]:
    """Repair Groq-confirmed bad fields from normalized provider metadata."""
    if not get_settings().groq_configured() or limit <= 0:
        return _empty_counts()

    rows = db.execute(
        select(CatalogQualityReview, Game)
        .join(Game, Game.id == CatalogQualityReview.game_id)
        .where(
            CatalogQualityReview.status == "needs_review",
            Game.content_type == "game",
        )
        .options(noload(Game.price_snapshots))
        .order_by(CatalogQualityReview.checked_at.asc(), CatalogQualityReview.id.asc())
        .limit(limit)
    ).all()
    counts = _empty_counts()
    for review, game in rows:
        counts["considered"] += 1
        try:
            outcome = await _repair_one(db, review, game)
        except Exception:
            log.exception("Catalog remediation failed for game_id=%d", game.id)
            db.rollback()
            persisted = db.get(CatalogQualityReview, review.id)
            if persisted is not None:
                _mark_pending(persisted, "failed")
                db.commit()
            counts["failed"] += 1
            continue
        counts[outcome] += 1
    return counts


async def _repair_one(
    db: Session,
    review: CatalogQualityReview,
    game: Game,
) -> str:
    fields = repair_fields(review.signals or [])
    if not fields:
        _mark_pending(review, "no_repairable_fields")
        db.commit()
        return "no_safe_change"

    researched = await research_game(db, game, fields)
    if not researched:
        _mark_pending(review, "no_provider_data")
        db.commit()
        return "no_provider_data"

    plan = build_repair_plan(game, review.signals or [], researched)
    if not plan.changes:
        _mark_pending(review, "no_consensus")
        db.commit()
        return "no_safe_change"
    if _title_conflicts(db, game, plan):
        _mark_pending(review, "title_conflict")
        db.commit()
        return "no_safe_change"

    now = datetime.now(UTC)
    snapshot = apply_repair_plan(game, plan, now)
    verdict = await ai_review(
        game,
        ["post_repair_verification", *(f"repaired:{field}" for field in plan.sources)],
        (),
    )
    if verdict is None or verdict.verdict != "OK":
        restore_repair(game, snapshot)
        _mark_pending(review, "verification_failed")
        db.add(game)
        db.commit()
        return "verification_failed"

    _persist_repair_evidence(db, game, plan, researched)
    refresh_game_seo_state(game, content_updated=True)
    review.status = "repaired"
    review.signals = [
        *[signal for signal in review.signals or [] if not signal.startswith("repair:")],
        *(f"repaired:{field}" for field in plan.sources),
        *(f"source:{field}={source}" for field, source in plan.sources.items()),
    ]
    review.reason = _repair_reason(plan, review.reason)
    review.checked_at = datetime.now(UTC)
    db.add_all([game, review])
    db.commit()
    _log_repair(game, plan)
    return "repaired"


def _persist_repair_evidence(
    db: Session,
    game: Game,
    plan: RepairPlan,
    researched: list[ResearchedGame],
) -> None:
    used_sources = set(plan.sources.values())
    for item in researched:
        record = item.record
        if record.source not in used_sources:
            continue
        store_source_snapshot(db, game, record, "catalog-quality/repair")
        upsert_external_id(
            db,
            game.id,
            record.source,
            record.external_id,
            slug=record.external_slug,
            url=record.external_url,
            confidence=_TRUSTED_CONFIDENCE if item.trusted_identity else _SEARCH_CONFIDENCE,
        )


def _mark_pending(review: CatalogQualityReview, code: str) -> None:
    review.status = "needs_review"
    review.signals = [
        *[signal for signal in review.signals or [] if not signal.startswith("repair:")],
        f"repair:{code}",
    ]
    review.checked_at = datetime.now(UTC)


def _title_conflicts(db: Session, game: Game, plan: RepairPlan) -> bool:
    title = plan.changes.get("title")
    if not isinstance(title, str):
        return False
    return db.scalar(
        select(func.count(Game.id)).where(
            Game.id != game.id,
            func.lower(Game.title) == title.casefold(),
        )
    ) not in (None, 0)


def _repair_reason(plan: RepairPlan, previous: str | None) -> str:
    details = ", ".join(f"{field}={source}" for field, source in sorted(plan.sources.items()))
    repaired = f"Repaired from normalized provider metadata ({details})."
    return f"{previous} | {repaired}" if previous else repaired


def _log_repair(game: Game, plan: RepairPlan) -> None:
    fields = ",".join(sorted(plan.sources))
    record_admin_event(
        username="system",
        action="catalog_quality_repair",
        method="JOB",
        path=f"/games/{game.slug}",
        status_code=200,
        query=f"fields={fields}",
    )


def _empty_counts() -> dict[str, int]:
    return {
        "considered": 0,
        "repaired": 0,
        "no_provider_data": 0,
        "no_safe_change": 0,
        "verification_failed": 0,
        "failed": 0,
    }
