"""Single-use account links: email verification and password reset.

Issuing a token invalidates any outstanding token of the same purpose, so only
the most recent link in a user's mailbox ever works.
"""

from __future__ import annotations

from datetime import timedelta
from secrets import token_urlsafe
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..account_security import hash_secret, utcnow
from ..config import get_settings
from ..models import AccountToken, User
from .account_email import send_account_email

TokenPurpose = Literal["verify_email", "reset_password"]

VERIFY_EMAIL_TTL_HOURS = 24
RESET_PASSWORD_TTL_HOURS = 1

_TOKEN_BYTES = 48


def issue_token(db: Session, user: User, purpose: TokenPurpose, ttl_hours: int) -> str:
    now = utcnow()
    for outstanding in db.scalars(
        select(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
        )
    ).all():
        outstanding.consumed_at = now

    raw = token_urlsafe(_TOKEN_BYTES)
    db.add(
        AccountToken(
            id=str(uuid4()),
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_secret(raw),
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            consumed_at=None,
        )
    )
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: TokenPurpose) -> User | None:
    """Returns the owning user and marks the token used, or None if unusable."""
    row = db.scalar(
        select(AccountToken)
        .where(
            AccountToken.token_hash == hash_secret(raw),
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
        )
        .with_for_update()
    )
    if row is None or _is_expired(row):
        return None
    user = db.scalar(select(User).where(User.id == row.user_id, User.is_active.is_(True)))
    if user is None:
        return None
    row.consumed_at = utcnow()
    return user


def _is_expired(row: AccountToken) -> bool:
    now = utcnow()
    expires_at = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or now.tzinfo)
    return expires_at <= now


async def send_verification_email(db: Session, user: User) -> None:
    raw = issue_token(db, user, "verify_email", VERIFY_EMAIL_TTL_HOURS)
    link = f"{get_settings().ACCOUNT_BASE_URL}/verify-email#token={raw}"
    await send_account_email(
        user.email,
        "Verify your GameMetrix account",
        f"Welcome to GameMetrix. Verify your email using this link:\n\n{link}"
        f"\n\nThis link expires in {VERIFY_EMAIL_TTL_HOURS} hours.",
    )


async def send_password_reset_email(db: Session, user: User) -> None:
    raw = issue_token(db, user, "reset_password", RESET_PASSWORD_TTL_HOURS)
    link = f"{get_settings().ACCOUNT_BASE_URL}/reset-password#token={raw}"
    await send_account_email(
        user.email,
        "Reset your GameMetrix password",
        f"Reset your password using this link:\n\n{link}\n\nThis link expires in one hour.",
    )
