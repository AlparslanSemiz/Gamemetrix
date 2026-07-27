"""Record and read AI-driven catalog mutations."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import AiCatalogChange, Game

_MAX_VALUE_CHARS = 1_000


def _json_safe(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value[:_MAX_VALUE_CHARS]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_VALUE_CHARS]


def record_ai_catalog_change(
    db: Session,
    game: Game,
    *,
    change_type: str,
    before: dict[str, object],
    after: dict[str, object],
    reason: str | None = None,
) -> AiCatalogChange | None:
    fields = sorted(
        field
        for field in set(before) | set(after)
        if _json_safe(before.get(field)) != _json_safe(after.get(field))
    )
    if not fields:
        return None
    row = AiCatalogChange(
        game_id=game.id,
        game_title=game.title,
        game_slug=game.slug,
        change_type=change_type[:48],
        fields=fields,
        before_values={field: _json_safe(before.get(field)) for field in fields},
        after_values={field: _json_safe(after.get(field)) for field in fields},
        reason=(reason or "")[:1_000] or None,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    return row


def recent_ai_catalog_changes(db: Session, *, limit: int) -> list[dict[str, object]]:
    rows = db.scalars(
        select(AiCatalogChange)
        .order_by(desc(AiCatalogChange.created_at), desc(AiCatalogChange.id))
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "game_id": row.game_id,
            "game_title": row.game_title,
            "game_slug": row.game_slug,
            "change_type": row.change_type,
            "fields": row.fields,
            "before": row.before_values,
            "after": row.after_values,
            "reason": row.reason,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
