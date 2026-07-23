"""Mapping a verified Google profile onto a local User."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..account_security import normalize_email, revoke_user_sessions, utcnow
from ..models import AccountToken, OAuthIdentity, User
from .account_state import get_or_create_preference

PROVIDER = "google"

_MAX_SUBJECT_LENGTH = 255
_MAX_EMAIL_LENGTH = 320
_MAX_DISPLAY_NAME_LENGTH = 80


class GoogleIdentityError(ValueError):
    """Google's profile response cannot be trusted as an account identity."""


class AccountDisabledError(RuntimeError):
    """The matched local account has been deactivated."""


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    display_name: str


@dataclass(frozen=True)
class ResolvedAccount:
    user: User
    created: bool


def validated_identity(userinfo: dict[str, object]) -> GoogleIdentity:
    subject = str(userinfo.get("sub") or "")
    email = normalize_email(str(userinfo.get("email") or ""))
    fallback_name = email.split("@", 1)[0]
    display_name = " ".join(str(userinfo.get("name") or fallback_name).split())[
        :_MAX_DISPLAY_NAME_LENGTH
    ]
    if (
        not subject
        or len(subject) > _MAX_SUBJECT_LENGTH
        or not email
        or len(email) > _MAX_EMAIL_LENGTH
        or not display_name
        or userinfo.get("email_verified") is not True
    ):
        raise GoogleIdentityError("Google did not return a verified email.")
    return GoogleIdentity(subject=subject, email=email, display_name=display_name)


def resolve_account(db: Session, identity: GoogleIdentity) -> ResolvedAccount:
    oauth_identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == PROVIDER,
            OAuthIdentity.provider_subject == identity.subject,
        )
    )
    user = (
        db.get(User, oauth_identity.user_id)
        if oauth_identity
        else db.scalar(select(User).where(User.email == identity.email))
    )

    now = utcnow()
    created = user is None
    if user is None:
        user = _create_user(db, identity, now)
    if not user.is_active:
        raise AccountDisabledError("This account is disabled.")

    if user.email_verified_at is None:
        # A verified Google identity may adopt a pending local address, but must
        # not inherit its untrusted password or outstanding account tokens.
        discard_unverified_local_credentials(db, user, now)
    user.email_verified_at = user.email_verified_at or now

    if oauth_identity is None:
        db.add(
            OAuthIdentity(
                id=str(uuid4()),
                user_id=user.id,
                provider=PROVIDER,
                provider_subject=identity.subject,
                created_at=now,
            )
        )
    db.commit()
    return ResolvedAccount(user=user, created=created)


def _create_user(db: Session, identity: GoogleIdentity, now: datetime) -> User:
    user = User(
        id=str(uuid4()),
        email=identity.email,
        display_name=identity.display_name,
        password_hash=None,
        email_verified_at=now,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    db.add(user)
    get_or_create_preference(db, user.id)
    db.flush()
    return user


def discard_unverified_local_credentials(db: Session, user: User, now: datetime) -> None:
    user.password_hash = None
    for token in db.scalars(
        select(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.consumed_at.is_(None),
        )
    ).all():
        token.consumed_at = now
    revoke_user_sessions(db, user.id)
