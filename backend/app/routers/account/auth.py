"""Registration, email verification, login/logout and password recovery."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...account_security import (
    AccountPrincipal,
    clear_account_cookies,
    create_account_session,
    hash_password_async,
    normalize_email,
    optional_account_principal,
    password_needs_rehash,
    require_account_principal,
    require_csrf,
    require_same_origin,
    revoke_user_sessions,
    set_account_cookies,
    utcnow,
    verify_password_async,
)
from ...config import get_settings
from ...database import get_db
from ...models import AnalyticsEvent, User, VisitEvent
from ...rate_limit import limiter
from ...services.account_email import email_delivery_ready
from ...services.account_state import account_payload, get_or_create_preference
from ...services.account_tokens import (
    consume_token,
    send_password_reset_email,
    send_verification_email,
)
from .schemas import (
    DeleteAccountPayload,
    ForgotPasswordPayload,
    LoginPayload,
    MessageResponse,
    RegisterPayload,
    ResetPasswordPayload,
    VerifyEmailPayload,
)

log = logging.getLogger(__name__)
router = APIRouter()

VERIFY_RATE_LIMIT = "10/minute"

_MIN_EMAIL_NAME_FOR_PASSWORD_CHECK = 3
_INVALID_LINK_DETAIL = "This link is invalid or has expired."
_CHECK_EMAIL_MESSAGE = "Check your email to continue."


def _reject_email_derived_password(email: str, password: str) -> None:
    email_name = email.split("@", 1)[0]
    if len(email_name) >= _MIN_EMAIL_NAME_FOR_PASSWORD_CHECK and email_name in password.casefold():
        raise HTTPException(status_code=422, detail="Password must not contain your email name.")


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def register(
    request: Request,
    payload: RegisterPayload,
    db: Session = Depends(get_db),
) -> MessageResponse:
    require_same_origin(request)
    if not email_delivery_ready():
        raise HTTPException(status_code=503, detail="Account email delivery is not configured.")

    email = normalize_email(str(payload.email))
    _reject_email_derived_password(email, payload.password)
    password_hash = await hash_password_async(payload.password)

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        await _replace_pending_registration(db, existing, payload, password_hash)
        return MessageResponse(message=_CHECK_EMAIL_MESSAGE)

    user = _create_pending_user(db, email, payload.display_name, password_hash)
    try:
        await send_verification_email(db, user)
    except Exception as exc:
        log.exception("Could not send account verification")
        raise HTTPException(
            status_code=503,
            detail="Verification email could not be sent. Try again shortly.",
        ) from exc
    return MessageResponse(message=_CHECK_EMAIL_MESSAGE)


async def _replace_pending_registration(
    db: Session,
    existing: User,
    payload: RegisterPayload,
    password_hash: str,
) -> None:
    """A new registration for an unverified address replaces the pending credentials.

    Only the mailbox owner can complete verification, so an attacker cannot
    permanently reserve a victim's email/password.
    """
    if existing.email_verified_at is not None or not existing.is_active:
        return
    existing.display_name = payload.display_name
    existing.password_hash = password_hash
    existing.updated_at = utcnow()
    revoke_user_sessions(db, existing.id)
    try:
        await send_verification_email(db, existing)
    except Exception:
        log.exception("Could not resend account verification")


def _create_pending_user(db: Session, email: str, display_name: str, password_hash: str) -> User:
    now = utcnow()
    user = User(
        id=str(uuid4()),
        email=email,
        display_name=display_name,
        password_hash=password_hash,
        email_verified_at=None,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    db.add(user)
    get_or_create_preference(db, user.id)
    db.commit()
    return user


@router.post("/email/verify", response_model=MessageResponse)
@limiter.limit(VERIFY_RATE_LIMIT)
async def verify_email(
    request: Request,
    payload: VerifyEmailPayload,
    db: Session = Depends(get_db),
) -> MessageResponse:
    require_same_origin(request)
    user = consume_token(db, payload.token, "verify_email")
    if user is None:
        raise HTTPException(status_code=400, detail=_INVALID_LINK_DETAIL)
    if not await verify_password_async(payload.password, user.password_hash):
        # The token proves control of the mailbox; the password proves this is
        # the person who initiated the pending registration.
        raise HTTPException(status_code=400, detail="This link or password is invalid.")
    user.email_verified_at = utcnow()
    user.updated_at = utcnow()
    db.commit()
    return MessageResponse(message="Email verified. You can now log in.")


@router.post("/login")
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def login(
    request: Request,
    response: Response,
    payload: LoginPayload,
    db: Session = Depends(get_db),
) -> dict:
    require_same_origin(request)
    user = db.scalar(select(User).where(User.email == normalize_email(str(payload.email))))
    password_matches = await verify_password_async(
        payload.password,
        user.password_hash if user else None,
    )
    if user is None or not user.is_active or not password_matches:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Verify your email before logging in.")

    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = await hash_password_async(payload.password)
    session_token, csrf_token = create_account_session(db, user, request)
    set_account_cookies(response, session_token, csrf_token)
    return {"account": account_payload(user)}


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MessageResponse:
    principal.session.revoked_at = utcnow()
    db.commit()
    clear_account_cookies(response)
    return MessageResponse(message="Logged out.")


@router.get("/me")
def me(principal: AccountPrincipal = Depends(require_account_principal)) -> dict:
    return {"account": account_payload(principal.user)}


@router.get("/session")
def account_session(
    principal: AccountPrincipal | None = Depends(optional_account_principal),
) -> dict:
    return {"account": account_payload(principal.user) if principal else None}


@router.post("/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordPayload,
    db: Session = Depends(get_db),
) -> MessageResponse:
    require_same_origin(request)
    user = db.scalar(
        select(User).where(
            User.email == normalize_email(str(payload.email)),
            User.is_active.is_(True),
        )
    )
    if user is not None and user.password_hash and email_delivery_ready():
        try:
            await send_password_reset_email(db, user)
        except Exception:
            log.exception("Could not send password reset email")
    return MessageResponse(message="If that account exists, a reset email has been sent.")


@router.post("/password/reset", response_model=MessageResponse)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def reset_password(
    request: Request,
    response: Response,
    payload: ResetPasswordPayload,
    db: Session = Depends(get_db),
) -> MessageResponse:
    require_same_origin(request)
    user = consume_token(db, payload.token, "reset_password")
    if user is None:
        raise HTTPException(status_code=400, detail=_INVALID_LINK_DETAIL)
    _reject_email_derived_password(user.email, payload.password)

    user.password_hash = await hash_password_async(payload.password)
    user.email_verified_at = user.email_verified_at or utcnow()
    user.updated_at = utcnow()
    revoke_user_sessions(db, user.id)
    db.commit()
    clear_account_cookies(response)
    return MessageResponse(message="Password reset. Log in with your new password.")


# Registered on the parent router in __init__.py: FastAPI rejects an empty path
# on a sub-router, and DELETE /api/account is the published contract.
async def delete_account(
    response: Response,
    payload: DeleteAccountPayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = principal.user
    if user.password_hash and not await verify_password_async(
        payload.current_password or "",
        user.password_hash,
    ):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.user_id == user.id))
    db.execute(delete(VisitEvent).where(VisitEvent.user_id == user.id))
    db.delete(user)
    db.commit()
    clear_account_cookies(response)
    return MessageResponse(message="Account deleted.")
