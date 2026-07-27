"""Audit trail for a refresh: rating snapshots, raw source snapshots, external IDs."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ExternalId, Game, RatingSnapshot, SourceSnapshot
from ..types import ExternalScore
from .constants import CRITIC_RATING_SOURCES, USER_RATING_SOURCES
from .values import review_count, score_value

_LIVE_CONFIDENCE = 0.95
_STALE_CONFIDENCE = 0.6
_DEFAULT_SCALE = 100

ExternalIdParts = tuple[str, str, str | None, str | None]


def external_id_from_score(score: ExternalScore) -> ExternalIdParts | None:
    raw = score.raw or {}
    if score.source == "Steam" and raw.get("steam_app_id"):
        app_id = str(raw["steam_app_id"])
        return ("Steam", app_id, None, f"https://store.steampowered.com/app/{app_id}/")
    if score.source == "IGDB" and raw.get("igdb_id"):
        return ("IGDB", str(raw["igdb_id"]), raw.get("igdb_slug"), raw.get("igdb_url"))  # type: ignore[arg-type]
    if score.source == "OpenCritic" and raw.get("opencritic_id"):
        opencritic_id = str(raw["opencritic_id"])
        return ("OpenCritic", opencritic_id, None, f"https://opencritic.com/game/{opencritic_id}/")
    if score.source == "Metacritic" and raw.get("rawg_id"):
        return ("RAWG", str(raw["rawg_id"]), raw.get("rawg_slug"), raw.get("rawg_url"))  # type: ignore[arg-type]
    return None


def _upsert_external_id_from_score(
    db: Session, game: Game, score: ExternalScore, now: datetime
) -> None:
    external = external_id_from_score(score)
    if external is None:
        return
    source, external_id, external_slug, external_url = external
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == source,
        )
    )
    if existing:
        existing.external_id = external_id
        existing.external_slug = external_slug
        existing.external_url = external_url
        existing.updated_at = now
        return
    db.add(
        ExternalId(
            game_id=game.id,
            source=source,
            external_id=external_id,
            external_slug=external_slug,
            external_url=external_url,
            confidence=_LIVE_CONFIDENCE if score.status == "live" else _STALE_CONFIDENCE,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
    )


def _raw_payload(score: ExternalScore) -> dict[str, object]:
    return {
        "source": score.source,
        "status": score.status,
        "score": score.score,
        "scale": score.scale,
        "detail": score.detail,
        "review_count": score.review_count,
        "raw": score.raw or {},
    }


def _rating_snapshot(
    game: Game, score: ExternalScore, applicable: frozenset[str], now: datetime
) -> RatingSnapshot:
    normalized = (
        round((score.score / score.scale) * 100, 1)
        if score.scale and score.score > 0
        else None
    )
    is_critic = score.source in CRITIC_RATING_SOURCES
    is_user = score.source in USER_RATING_SOURCES
    return RatingSnapshot(
        game_id=game.id,
        source=score.source,
        score=score.score if score.score > 0 else None,
        score_normalized=normalized,
        rating_count=score.review_count,
        review_count=score.review_count,
        critic_count=score.review_count if is_critic else None,
        user_count=score.review_count if is_user else None,
        is_critic=is_critic,
        is_user=is_user,
        is_applicable=score.source in applicable or score.source == "RAWG",
        confidence=1.0 if score.status == "live" else 0.0,
        raw_payload=_raw_payload(score),
        fetched_at=now,
        created_at=now,
    )


def _source_snapshot(game: Game, score: ExternalScore, now: datetime) -> SourceSnapshot:
    external = external_id_from_score(score)
    external_id = str((external or ("", "", None, None))[1] or "") or None
    return SourceSnapshot(
        source=score.source,
        endpoint="rating-refresh",
        query=game.title,
        external_id=external_id,
        status_code=None,
        raw_payload=_raw_payload(score),
        fetched_at=now,
        created_at=now,
    )


def _same_rating_snapshot(current: RatingSnapshot, candidate: RatingSnapshot) -> bool:
    """Ignore refresh timestamps when deciding whether audit state changed."""
    return (
        current.score == candidate.score
        and current.score_normalized == candidate.score_normalized
        and current.rating_count == candidate.rating_count
        and current.review_count == candidate.review_count
        and current.critic_count == candidate.critic_count
        and current.user_count == candidate.user_count
        and current.is_critic == candidate.is_critic
        and current.is_user == candidate.is_user
        and current.is_applicable == candidate.is_applicable
        and current.confidence == candidate.confidence
        and current.raw_payload == candidate.raw_payload
    )


def persist_source_records(db: Session, game: Game, scores: list[ExternalScore]) -> None:
    now = datetime.now(UTC)
    applicable = game.applicable_primary_sources
    for score in scores:
        candidate = _rating_snapshot(game, score, applicable, now)
        current = db.scalar(
            select(RatingSnapshot)
            .where(
                RatingSnapshot.game_id == game.id,
                RatingSnapshot.source == score.source,
            )
            .order_by(RatingSnapshot.fetched_at.desc(), RatingSnapshot.id.desc())
            .limit(1)
        )
        if current is None or not _same_rating_snapshot(current, candidate):
            db.add(candidate)
            db.add(_source_snapshot(game, score, now))
        _upsert_external_id_from_score(db, game, score, now)


def backfill_current_source_records(db: Session, game: Game) -> int:
    """Persist current Game.source_scores into audit tables once per source."""
    scores = [
        score
        for row in (game.source_scores or [])
        if (score := _score_from_stored_row(db, game, row)) is not None
    ]
    if not scores:
        return 0
    persist_source_records(db, game, scores)
    return len(scores)


def _score_from_stored_row(db: Session, game: Game, row: dict[str, object]) -> ExternalScore | None:
    source = str(row.get("source", ""))
    if not source:
        return None
    already_recorded = db.scalar(
        select(RatingSnapshot.id)
        .where(RatingSnapshot.game_id == game.id, RatingSnapshot.source == source)
        .limit(1)
    )
    if already_recorded:
        return None
    try:
        return ExternalScore(
            source=source,
            score=score_value(row) or 0.0,
            scale=int(row.get("scale", _DEFAULT_SCALE) or _DEFAULT_SCALE),
            status=str(row.get("status", "live")),  # type: ignore[arg-type]
            detail=(str(row.get("detail", "")) or None),
            review_count=review_count(row),
            raw={"source_score": row},
        )
    except (TypeError, ValueError, OverflowError):
        return None
