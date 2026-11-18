"""Who may set `games.steam_app_id`, and how a doubtful id is queued for review.

Every writer of the id goes through `claim_steam_app_id`, so a low-confidence
source (an IGDB cross-reference, a title search) can fill a gap but can never
overwrite an id that appdetails already confirmed.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..content_type import content_type_from_steam_type
from ..integrations.steam.identity import SteamIdentity, steam_identity_verdict
from ..integrations.steam_service import steam_service
from ..integrations.types import NormalizedGame
from ..models import CatalogQualityReview, ExternalId, Game

STEAM_REVIEW_SIGNAL = "steam_id_mismatch"
VERIFIED_CONFIDENCE = 1.0
UNVERIFIED_CONFIDENCE = 0.85


def identity_from_result(game: Game, result: NormalizedGame) -> SteamIdentity:
    """Verdict for a normalized appdetails result against a catalog row."""
    release = result.release_date
    return steam_identity_verdict(
        game.title,
        game.release_year,
        steam_name=result.name,
        steam_year=release.year if release else None,
        steam_type=str(result.raw.get("steam_type") or "game"),
    )


def claim_steam_app_id(
    db: Session,
    game: Game,
    app_id: int,
    *,
    verified: bool,
    now: datetime | None = None,
) -> bool:
    """Try to make `app_id` the game's Steam id. True when the row changed.

    - no id yet: any source may set it (marked verified only if appdetails agreed);
    - same id: a verification just stamps it;
    - different id: only a verified claim may replace it, and an unverified claim
      never replaces anything.
    """
    # Lazy: the metadata_backfill package imports this module.
    from .metadata_backfill.persistence import upsert_external_id

    now = now or datetime.now(UTC)
    current = game.steam_app_id
    if current is not None and current != app_id:
        if not verified:
            return False
        _drop_steam_external_id(db, game)
    changed = current != app_id
    game.steam_app_id = app_id
    if verified:
        if game.steam_app_id_verified_at is None or changed:
            game.steam_app_id_verified_at = now
            changed = True
    elif changed:
        game.steam_app_id_verified_at = None
    upsert_external_id(
        db,
        game.id,
        "Steam",
        str(app_id),
        url=steam_service.store_url(app_id),
        confidence=VERIFIED_CONFIDENCE if verified else UNVERIFIED_CONFIDENCE,
    )
    db.add(game)
    return changed


def _drop_steam_external_id(db: Session, game: Game) -> None:
    for row in db.scalars(
        select(ExternalId).where(ExternalId.game_id == game.id, ExternalId.source == "Steam")
    ).all():
        db.delete(row)
    db.flush()


def clear_steam_app_id(db: Session, game: Game) -> None:
    """Remove a refuted id (column, verification stamp and Steam external id)."""
    game.steam_app_id = None
    game.steam_app_id_verified_at = None
    _drop_steam_external_id(db, game)
    db.add(game)


def queue_steam_review(db: Session, game: Game, reason: str, *, now: datetime | None = None) -> None:
    """Put the game on the admin review queue (`catalog_quality_reviews`, needs_review)."""
    now = now or datetime.now(UTC)
    review = db.scalar(select(CatalogQualityReview).where(CatalogQualityReview.game_id == game.id))
    if review is None:
        review = CatalogQualityReview(game_id=game.id, status="needs_review", signals=[], checked_at=now)
    signals = list(review.signals or [])
    if STEAM_REVIEW_SIGNAL not in signals:
        signals.append(STEAM_REVIEW_SIGNAL)
    review.signals = signals
    if review.status != "quarantined":
        review.status = "needs_review"
    review.reason = reason[:500]
    review.checked_at = now
    db.add(review)


def apply_steam_product_type(game: Game, identity: SteamIdentity) -> bool:
    """Reclassify a "game" row whose own Steam page is a DLC / soundtrack / demo.

    Only when the name matched (so the id is the right product) and only from
    `game`: rows already classified, including AI-confirmed `non-game`, stay as is.
    """
    target = content_type_from_steam_type(identity.steam_type)
    if not identity.name_matches or target is None or game.content_type != "game":
        return False
    game.content_type = target
    return True
