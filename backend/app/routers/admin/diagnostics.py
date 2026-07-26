"""Read-only per-game inspection: external IDs, rating and source snapshots."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import (
    CatalogQualityReview,
    ExternalId,
    Game,
    RatingSnapshot,
    SourceSnapshot,
    UserCollection,
)
from ...security import AuthenticatedUser, require_admin_user
from ...services.admin_audit import record_admin_event
from ...account_security import utcnow
from ._common import game_id_path, get_game_or_404

router = APIRouter()


class CatalogQualityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "quarantine", "delete"]


@router.get("/catalog-quality")
def get_catalog_quality(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    counts = {
        status: count
        for status, count in db.execute(
            select(CatalogQualityReview.status, func.count(CatalogQualityReview.id))
            .group_by(CatalogQualityReview.status)
            .order_by(CatalogQualityReview.status)
        )
    }
    rows = db.execute(
        select(CatalogQualityReview, Game.title, Game.slug)
        .join(Game, Game.id == CatalogQualityReview.game_id)
        .where(CatalogQualityReview.status.in_(("needs_review", "quarantined")))
        .order_by(CatalogQualityReview.checked_at.desc())
        .limit(limit)
    ).all()
    return {
        "status_counts": counts,
        "issues": [
            {
                "game_id": review.game_id,
                "title": title,
                "slug": slug,
                "status": review.status,
                "signals": review.signals,
                "reason": review.reason,
                "checked_at": review.checked_at.isoformat(),
            }
            for review, title, slug in rows
        ],
    }


@router.post("/catalog-quality/{game_id}/decision")
def decide_catalog_quality(
    payload: CatalogQualityDecision,
    game_id: int = game_id_path(),
    admin: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    game = get_game_or_404(db, game_id)
    review = db.scalar(
        select(CatalogQualityReview)
        .where(CatalogQualityReview.game_id == game_id)
        .with_for_update()
    )
    if review is None:
        raise HTTPException(status_code=409, detail="No catalog-quality review is pending.")

    if payload.decision == "delete":
        references = db.scalar(
            select(func.count(UserCollection.id)).where(UserCollection.game_id == game_id)
        ) or 0
        if references:
            raise HTTPException(
                status_code=409,
                detail="A game in user collections cannot be deleted; quarantine it instead.",
            )
        db.delete(game)
        db.commit()
        _record_catalog_decision(admin.username, game_id, payload.decision)
        return {"game_id": game_id, "decision": payload.decision, "deleted": True}

    game.content_type = "game" if payload.decision == "approve" else "non-game"
    if payload.decision == "quarantine":
        game.data_complete = False
    review.status = "approved" if payload.decision == "approve" else "quarantined"
    review.checked_at = utcnow()
    db.add(game)
    db.add(review)
    db.commit()
    _record_catalog_decision(admin.username, game_id, payload.decision)
    return {
        "game_id": game_id,
        "decision": payload.decision,
        "deleted": False,
        "status": review.status,
    }


def _record_catalog_decision(
    username: str,
    game_id: int,
    decision: str,
) -> None:
    record_admin_event(
        username=username,
        action="catalog_quality_decision",
        method="POST",
        path=f"/admin/catalog-quality/{game_id}/decision",
        status_code=200,
        query=f"decision={decision}",
    )


@router.get("/external-ids/{game_id}")
def get_external_ids(game_id: int = game_id_path(), db: Session = Depends(get_db)) -> dict:
    game = get_game_or_404(db, game_id)
    rows = db.scalars(select(ExternalId).where(ExternalId.game_id == game_id)).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "external_ids": [_external_id_row(row) for row in rows],
    }


def _external_id_row(row: ExternalId) -> dict[str, object]:
    return {
        "source": row.source,
        "external_id": row.external_id,
        "external_slug": row.external_slug,
        "external_url": row.external_url,
        "confidence": row.confidence,
        "is_primary": row.is_primary,
    }


@router.get("/rating-snapshots/{game_id}")
def get_rating_snapshots(game_id: int = game_id_path(), db: Session = Depends(get_db)) -> dict:
    game = get_game_or_404(db, game_id)
    rows = db.scalars(
        select(RatingSnapshot)
        .where(RatingSnapshot.game_id == game_id)
        .order_by(RatingSnapshot.fetched_at.desc())
    ).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "snapshots": [_rating_snapshot_row(row) for row in rows],
    }


def _rating_snapshot_row(row: RatingSnapshot) -> dict[str, object]:
    return {
        "source": row.source,
        "score": row.score,
        "score_normalized": row.score_normalized,
        "rating_count": row.rating_count,
        "is_critic": row.is_critic,
        "is_user": row.is_user,
        "is_applicable": row.is_applicable,
        "confidence": row.confidence,
        "fetched_at": row.fetched_at.isoformat(),
        "raw_payload": row.raw_payload,
    }


@router.get("/source-snapshots/{game_id}")
def get_source_snapshots(game_id: int = game_id_path(), db: Session = Depends(get_db)) -> dict:
    game = get_game_or_404(db, game_id)
    rows = db.scalars(
        select(SourceSnapshot)
        .where(SourceSnapshot.query == game.title)
        .order_by(SourceSnapshot.fetched_at.desc())
    ).all()
    return {
        "game_id": game_id,
        "title": game.title,
        "snapshots": [_source_snapshot_row(row) for row in rows],
    }


def _source_snapshot_row(row: SourceSnapshot) -> dict[str, object]:
    return {
        "source": row.source,
        "endpoint": row.endpoint,
        "query": row.query,
        "external_id": row.external_id,
        "status_code": row.status_code,
        "fetched_at": row.fetched_at.isoformat(),
        "raw_payload": row.raw_payload,
    }
