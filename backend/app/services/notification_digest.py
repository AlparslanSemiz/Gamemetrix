from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..database import SessionLocal
from ..models import Game, NotificationDelivery, User, UserCollection, UserPreference
from .account_email import send_account_email


log = logging.getLogger(__name__)


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _unsubscribe_token(user_id: str) -> str:
    cfg = get_settings()
    return jwt.encode(
        {
            "sub": user_id,
            "purpose": "unsubscribe_digest",
            "exp": datetime.now(UTC) + timedelta(days=90),
        },
        cfg.JWT_SECRET_KEY,
        algorithm="HS256",
    )


def _candidate_lines(game: Game, pref: UserPreference, now: datetime) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    prices = sorted(
        (
            item for item in game.price_snapshots
            if item.fetched_at.replace(tzinfo=item.fetched_at.tzinfo or UTC) >= now - timedelta(hours=24)
        ),
        key=lambda item: (item.discount_percent or 0, -(item.sale_price or 0)),
        reverse=True,
    )
    free = next((item for item in prices if item.is_free or item.sale_price == 0), None)
    deal = next((item for item in prices if (item.discount_percent or 0) >= pref.alert_min_discount), None)
    if free:
        rows.append((
            _fingerprint(f"{game.slug}:free:{free.store}"),
            f"{game.title} is free at {free.store}.",
        ))
    elif deal:
        price = f"{deal.sale_price:g} {deal.currency}" if deal.sale_price is not None else "sale price available"
        rows.append((
            _fingerprint(f"{game.slug}:deal:{deal.store}:{deal.discount_percent}:{deal.sale_price}"),
            f"{game.title} is {deal.discount_percent}% off at {deal.store} ({price}).",
        ))
    release = datetime.combine(game.release_date, datetime.min.time(), tzinfo=UTC)
    if now <= release <= now + timedelta(days=pref.alert_upcoming_days):
        rows.append((
            _fingerprint(f"{game.slug}:release:{game.release_date.isoformat()}"),
            f"{game.title} releases on {game.release_date.isoformat()}.",
        ))
    if game.metrix_score >= pref.alert_min_score:
        rounded = round(game.metrix_score)
        rows.append((
            _fingerprint(f"{game.slug}:score:{rounded}"),
            f"{game.title} has reached a GameMetrix score of {rounded}.",
        ))
    return rows


async def send_notification_digests() -> int:
    cfg = get_settings()
    if not cfg.ACCOUNT_AUTH_ENABLED or len(cfg.JWT_SECRET_KEY) < 32:
        return 0
    sent = 0
    with SessionLocal() as db:
        preferences = db.scalars(
            select(UserPreference).where(UserPreference.email_digest_enabled.is_(True))
        ).all()
        now = datetime.now(UTC)
        for pref in preferences:
            user = db.scalar(
                select(User).where(
                    User.id == pref.user_id,
                    User.is_active.is_(True),
                    User.email_verified_at.is_not(None),
                )
            )
            if user is None:
                continue
            games = db.scalars(
                select(Game)
                .join(UserCollection, UserCollection.game_id == Game.id)
                .where(
                    UserCollection.user_id == user.id,
                    UserCollection.collection_type == "watchlist",
                )
                .options(selectinload(Game.price_snapshots))
                .order_by(Game.rank_score.desc(), Game.title)
                .limit(500)
            ).unique().all()
            candidates = [item for game in games for item in _candidate_lines(game, pref, now)]
            candidate_fingerprints = {fingerprint for fingerprint, _ in candidates}
            if not candidate_fingerprints:
                continue
            existing = set(
                db.scalars(
                    select(NotificationDelivery.fingerprint).where(
                        NotificationDelivery.user_id == user.id,
                        NotificationDelivery.fingerprint.in_(candidate_fingerprints),
                    )
                ).all()
            )
            fresh = [item for item in candidates if item[0] not in existing][:100]
            if not fresh:
                continue
            unsubscribe = f"{cfg.ACCOUNT_BASE_URL}/api/account/email/unsubscribe?token={_unsubscribe_token(user.id)}"
            body = "Your GameMetrix watchlist updates:\n\n" + "\n".join(f"- {line}" for _, line in fresh)
            body += f"\n\nManage alerts in your account or unsubscribe: {unsubscribe}"
            await send_account_email(user.email, "Your GameMetrix watchlist updates", body)
            for fingerprint, _ in fresh:
                db.add(
                    NotificationDelivery(
                        user_id=user.id,
                        fingerprint=fingerprint,
                        channel="email",
                        delivered_at=now,
                    )
                )
            db.commit()
            sent += 1
    return sent


async def notification_digest_loop() -> None:
    await asyncio.sleep(300)
    while True:
        try:
            await send_notification_digests()
        except Exception:
            log.exception("Account notification digest failed")
        await asyncio.sleep(24 * 60 * 60)
