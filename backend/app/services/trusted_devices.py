"""Trusted browsers: a random cookie token, stored server-side only as its SHA-256."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_bytes

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import TrustedDevice

DEVICE_TTL_DAYS = 30
MAX_DEVICES_PER_USER = 10


def _hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def issue_device(db: Session, user_id: str, *, now: datetime | None = None) -> str:
    """Create a device token for the user and return the raw value for the cookie."""
    current = now or datetime.now(UTC)
    raw = token_bytes(32).hex()
    db.add(
        TrustedDevice(
            token_hash=_hash(raw),
            user_id=user_id,
            created_at=current,
            expires_at=current + timedelta(days=DEVICE_TTL_DAYS),
        )
    )
    db.flush()
    stale = db.scalars(
        select(TrustedDevice.token_hash)
        .where(TrustedDevice.user_id == user_id)
        .order_by(TrustedDevice.created_at.desc())
        .offset(MAX_DEVICES_PER_USER)
    ).all()
    if stale:
        db.execute(delete(TrustedDevice).where(TrustedDevice.token_hash.in_(stale)))
    db.commit()
    return raw


def is_trusted_device(db: Session, user_id: str, raw: str | None, *, now: datetime | None = None) -> bool:
    if not raw:
        return False
    row = db.get(TrustedDevice, _hash(raw))
    return row is not None and row.user_id == user_id and row.expires_at > (now or datetime.now(UTC))


def revoke_devices(db: Session, user_id: str) -> None:
    """Forget every trusted browser of this user (no commit: part of the caller's change)."""
    db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user_id))
