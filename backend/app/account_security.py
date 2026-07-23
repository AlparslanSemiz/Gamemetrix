from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from urllib.parse import urlparse
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import AccountSession, User


SESSION_COOKIE = "gm_session"
CSRF_COOKIE = "gm_csrf"
OAUTH_COOKIE = "gm_oauth"
MIN_SIGNING_SECRET_LENGTH = 32
LINK_SIGNING_ALGORITHM = "HS256"
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("GameMetrix timing-only password sentinel")


@dataclass(frozen=True)
class AccountPrincipal:
    user: User
    session: AccountSession


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def hash_secret(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def link_signing_secret() -> str | None:
    """The HS256 key for signed links and OAuth state, or None if unusably short."""
    secret = get_settings().JWT_SECRET_KEY
    return secret if len(secret) >= MIN_SIGNING_SECRET_LENGTH else None


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if len(password) > 1024:
        return False
    candidate_hash = password_hash or _DUMMY_PASSWORD_HASH
    try:
        matches = _PASSWORD_HASHER.verify(candidate_hash, password)
        return bool(password_hash) and matches
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def _network_hash(request: Request, header: str) -> str | None:
    value = request.headers.get(header)
    if not value:
        return None
    return hash_secret(f"{get_settings().analytics_salt()}:{value[:500]}")


def create_account_session(db: Session, user: User, request: Request) -> tuple[str, str]:
    now = utcnow()
    previous_token = request.cookies.get(SESSION_COOKIE)
    if previous_token:
        previous_session = db.scalar(
            select(AccountSession).where(AccountSession.token_hash == hash_secret(previous_token))
        )
        if previous_session is not None and previous_session.revoked_at is None:
            previous_session.revoked_at = now
    raw_token = token_urlsafe(48)
    raw_csrf = token_urlsafe(32)
    row = AccountSession(
        id=str(uuid4()),
        user_id=user.id,
        token_hash=hash_secret(raw_token),
        csrf_hash=hash_secret(raw_csrf),
        ip_hash=_network_hash(request, "x-real-ip"),
        user_agent_hash=_network_hash(request, "user-agent"),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=get_settings().ACCOUNT_SESSION_DAYS),
        revoked_at=None,
    )
    db.add(row)
    user.last_login_at = now
    user.updated_at = now
    db.commit()
    return raw_token, raw_csrf


def set_account_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    cfg = get_settings()
    max_age = cfg.ACCOUNT_SESSION_DAYS * 24 * 60 * 60
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=cfg.is_production,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=cfg.is_production,
        samesite="lax",
        path="/",
    )


def clear_account_cookies(response: Response) -> None:
    secure = get_settings().is_production
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="lax")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def optional_account_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> AccountPrincipal | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    session = db.scalar(
        select(AccountSession).where(AccountSession.token_hash == hash_secret(raw))
    )
    if session is None or session.revoked_at is not None or _aware(session.expires_at) <= utcnow():
        return None
    user = db.scalar(select(User).where(User.id == session.user_id, User.is_active.is_(True)))
    if user is None:
        return None
    if utcnow() - _aware(session.last_seen_at) > timedelta(hours=1):
        session.last_seen_at = utcnow()
        db.commit()
    return AccountPrincipal(user=user, session=session)


def require_account_principal(
    principal: AccountPrincipal | None = Depends(optional_account_principal),
) -> AccountPrincipal:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account login required.")
    return principal


def require_account_enabled() -> None:
    if not get_settings().ACCOUNT_AUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Account login is temporarily unavailable.")


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        if get_settings().is_production:
            raise HTTPException(status_code=403, detail="Request origin is required.")
        return
    parsed = urlparse(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed = set(get_settings().CORS_ALLOW_ORIGINS)
    allowed.add(get_settings().ACCOUNT_BASE_URL)
    if normalized not in allowed:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


def require_csrf(
    request: Request,
    principal: AccountPrincipal = Depends(require_account_principal),
) -> AccountPrincipal:
    require_same_origin(request)
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    header_value = request.headers.get("x-csrf-token", "")
    if not cookie_value or not header_value or not compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    if not compare_digest(hash_secret(cookie_value), principal.session.csrf_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    return principal


def revoke_user_sessions(db: Session, user_id: str) -> None:
    now = utcnow()
    for session in db.scalars(
        select(AccountSession).where(
            AccountSession.user_id == user_id,
            AccountSession.revoked_at.is_(None),
        )
    ).all():
        session.revoked_at = now
    db.flush()
