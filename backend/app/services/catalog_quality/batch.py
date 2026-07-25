"""Persistent catalog-quality scan, verdict application and safe quarantine."""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, noload

from ...config import get_settings
from ...models import CatalogQualityReview, Game, UserCollection
from ..admin_audit import record_admin_event
from .review import QualityVerdict, ai_review
from .signals import catalog_quality_signals

_QUARANTINE_CONTENT_TYPE = "non-game"
_SCAN_MULTIPLIER = 25
_MAX_SCAN_ROWS = 2000


def _candidate_rows(
    db: Session,
    scan_limit: int,
) -> list[tuple[Game, CatalogQualityReview | None]]:
    duplicate_summaries = (
        select(Game.summary)
        .where(Game.content_type == "game", Game.summary != "")
        .group_by(Game.summary)
        .having(func.count(Game.id) > 1)
    )
    updated_after_review = or_(
        Game.metadata_refreshed_at > CatalogQualityReview.checked_at,
        Game.summary_refreshed_at > CatalogQualityReview.checked_at,
    )
    rows = db.execute(
        select(Game, CatalogQualityReview)
        .outerjoin(CatalogQualityReview, CatalogQualityReview.game_id == Game.id)
        .where(
            Game.content_type == "game",
            or_(CatalogQualityReview.id.is_(None), updated_after_review),
        )
        .options(noload(Game.price_snapshots))
        .order_by(
            Game.summary.in_(duplicate_summaries).desc(),
            Game.rank_score.asc(),
            Game.id.asc(),
        )
        .limit(scan_limit)
    ).all()
    return [(game, review) for game, review in rows]


def _duplicate_title_map(db: Session) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for summary, title in db.execute(
        select(Game.summary, Game.title).where(Game.content_type == "game")
    ):
        clean_summary = (summary or "").strip()
        if clean_summary:
            grouped.setdefault(clean_summary, []).append(title)
    return {
        summary: tuple(titles)
        for summary, titles in grouped.items()
        if len(titles) > 1
    }


def _other_duplicate_titles(
    game: Game,
    grouped: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return tuple(
        title
        for title in grouped.get((game.summary or "").strip(), ())
        if title != game.title
    )


def _store_review(
    db: Session,
    game: Game,
    review: CatalogQualityReview | None,
    *,
    status: str,
    signals: list[str],
    reason: str | None,
) -> None:
    row = review or CatalogQualityReview(game_id=game.id)
    row.status = status
    row.signals = signals
    row.reason = reason
    row.checked_at = datetime.now(UTC)
    db.add(row)


def _log_deletion(game: Game) -> None:
    record_admin_event(
        username="system",
        action="catalog_quality_delete",
        method="JOB",
        path=f"/games/{game.slug}",
        status_code=200,
        query="reason=strong_marker+ai",
    )


def _apply_verdict(
    db: Session,
    game: Game,
    review: CatalogQualityReview | None,
    signals: list[str],
    verdict: QualityVerdict,
) -> str:
    review_signals = [*signals, *(f"ai:{field}" for field in verdict.fields)]
    if verdict.verdict == "OK":
        _store_review(
            db,
            game,
            review,
            status="approved",
            signals=review_signals,
            reason=verdict.reason or None,
        )
        return "approved"
    if verdict.verdict == "BAD_METADATA":
        game.data_complete = False
        db.add(game)
        _store_review(
            db,
            game,
            review,
            status="needs_review",
            signals=review_signals,
            reason=verdict.reason or None,
        )
        return "needs_review"

    referenced = db.scalar(
        select(func.count(UserCollection.id)).where(UserCollection.game_id == game.id)
    ) or 0
    cfg = get_settings()
    if "non_game_marker" in signals and cfg.NONGAME_AUTODELETE_ENABLED and referenced == 0:
        _log_deletion(game)
        db.delete(game)
        return "deleted"

    game.content_type = _QUARANTINE_CONTENT_TYPE
    game.data_complete = False
    db.add(game)
    _store_review(
        db,
        game,
        review,
        status="quarantined",
        signals=review_signals,
        reason=verdict.reason or None,
    )
    return "quarantined"


async def catalog_quality_batch(db: Session, limit: int) -> dict[str, int]:
    """Review suspicious catalog rows and persist progress without trusting AI edits."""
    cfg = get_settings()
    if not cfg.groq_configured() or limit <= 0:
        return _empty_counts()

    scan_limit = min(_MAX_SCAN_ROWS, max(limit, limit * _SCAN_MULTIPLIER))
    grouped = _duplicate_title_map(db)
    rows = _candidate_rows(db, scan_limit)
    counts = _empty_counts()

    for game, review in rows:
        duplicate_titles = _other_duplicate_titles(game, grouped)
        signals = catalog_quality_signals(game, duplicate_titles)
        counts["scanned"] += 1
        if not signals:
            _store_review(
                db,
                game,
                review,
                status="not_required",
                signals=[],
                reason=None,
            )
            continue
        if counts["ai_checked"] >= limit:
            break

        counts["candidates"] += 1
        verdict = await ai_review(game, signals, duplicate_titles)
        if verdict is None:
            counts["unavailable"] += 1
            break
        counts["ai_checked"] += 1
        outcome = _apply_verdict(db, game, review, signals, verdict)
        counts[outcome] += 1

    db.commit()
    return counts


def _empty_counts() -> dict[str, int]:
    return {
        "scanned": 0,
        "candidates": 0,
        "ai_checked": 0,
        "approved": 0,
        "needs_review": 0,
        "quarantined": 0,
        "deleted": 0,
        "unavailable": 0,
    }
