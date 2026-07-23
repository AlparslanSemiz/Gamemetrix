"""RAWG ExternalId upserts and raw-response snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ExternalId, Game, SourceSnapshot
from .matching import rawg_game_url

_RAWG_CONFIDENCE = 0.92


def upsert_rawg_external_id(db: Session, game: Game, raw_game: dict) -> None:
    rawg_id = raw_game.get("id")
    if not rawg_id:
        return
    now = datetime.now(UTC)
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == "RAWG",
        )
    )
    if existing:
        existing.external_id = str(rawg_id)
        existing.external_slug = raw_game.get("slug")
        existing.external_url = rawg_game_url(raw_game)
        existing.updated_at = now
        return

    db.add(
        ExternalId(
            game_id=game.id,
            source="RAWG",
            external_id=str(rawg_id),
            external_slug=raw_game.get("slug"),
            external_url=rawg_game_url(raw_game),
            confidence=_RAWG_CONFIDENCE,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
    )


def store_rawg_snapshot(
    db: Session,
    endpoint: str,
    query: str,
    raw_payload: dict,
    status_code: int = 200,
    rawg_id: str | None = None,
) -> None:
    now = datetime.now(UTC)
    db.add(
        SourceSnapshot(
            source="RAWG",
            endpoint=endpoint,
            query=query,
            external_id=rawg_id,
            status_code=status_code,
            raw_payload=raw_payload,
            fetched_at=now,
            created_at=now,
        )
    )
