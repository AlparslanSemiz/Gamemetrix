"""ExternalId upserts and source-snapshot audit rows for the backfill."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...integrations.types import NormalizedGame
from ...models import ExternalId, Game, SourceSnapshot

DEFAULT_CONFIDENCE = 0.9


def has_external_id(db: Session, game: Game, source: str) -> bool:
    if not game.id:
        return False
    return db.scalar(
        select(ExternalId.id)
        .where(ExternalId.game_id == game.id, ExternalId.source == source)
        .limit(1)
    ) is not None


def upsert_external_id(
    db: Session,
    game_id: int,
    source: str,
    external_id: str,
    *,
    slug: str | None = None,
    url: str | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
) -> None:
    now = datetime.now(UTC)
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game_id,
            ExternalId.source == source,
        )
    )
    if existing:
        existing.external_id = external_id
        existing.external_slug = slug
        existing.external_url = url
        existing.confidence = max(existing.confidence, confidence)
        existing.updated_at = now
        return

    db.add(
        ExternalId(
            game_id=game_id,
            source=source,
            external_id=external_id,
            external_slug=slug,
            external_url=url,
            confidence=confidence,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
    )


def store_source_snapshot(db: Session, game: Game, result: NormalizedGame, endpoint: str) -> None:
    now = datetime.now(UTC)
    db.add(
        SourceSnapshot(
            source=result.source,
            endpoint=endpoint,
            query=game.title,
            external_id=result.external_id,
            status_code=None,
            raw_payload=result.raw,
            fetched_at=now,
            created_at=now,
        )
    )
