"""Alert preferences and the signed email-digest unsubscribe link."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ...account_security import (
    LINK_SIGNING_ALGORITHM,
    AccountPrincipal,
    link_signing_secret,
    require_csrf,
    utcnow,
)
from ...database import get_db
from ...models import UserPreference
from ...rate_limit import limiter
from ...services.account_state import (
    AccountStateLimitError,
    account_state_payload,
    get_or_create_preference,
    sanitized_settings,
)
from .schemas import MessageResponse, PreferencePatch

router = APIRouter()

UNSUBSCRIBE_RATE_LIMIT = "20/minute"

_UNSUBSCRIBE_PURPOSE = "unsubscribe_digest"
_INVALID_UNSUBSCRIBE_DETAIL = "Unsubscribe link is invalid or expired."
_MIN_UNSUBSCRIBE_TOKEN_LENGTH = 32
_MAX_UNSUBSCRIBE_TOKEN_LENGTH = 1024


@router.patch("/preferences")
def update_preferences(
    payload: PreferencePatch,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    preference = get_or_create_preference(db, principal.user.id)
    _apply_alert_thresholds(preference, payload)
    if payload.email_digest_enabled is not None:
        preference.email_digest_enabled = payload.email_digest_enabled
    if payload.marketing_enabled is not None:
        preference.marketing_enabled = payload.marketing_enabled
    if payload.settings is not None:
        try:
            preference.settings = sanitized_settings(
                dict(preference.settings or {}),
                dict(payload.settings),
            )
        except AccountStateLimitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    preference.updated_at = utcnow()
    db.commit()
    return account_state_payload(db, principal.user)["preferences"]


def _apply_alert_thresholds(preference: UserPreference, payload: PreferencePatch) -> None:
    if payload.min_discount is not None:
        preference.alert_min_discount = payload.min_discount
    if payload.min_score is not None:
        preference.alert_min_score = payload.min_score
    if payload.upcoming_days is not None:
        preference.alert_upcoming_days = payload.upcoming_days


@router.get("/email/unsubscribe", response_model=MessageResponse)
@limiter.limit(UNSUBSCRIBE_RATE_LIMIT)
def unsubscribe_email_digest(
    request: Request,
    token: str = Query(
        ...,
        min_length=_MIN_UNSUBSCRIBE_TOKEN_LENGTH,
        max_length=_MAX_UNSUBSCRIBE_TOKEN_LENGTH,
    ),
    db: Session = Depends(get_db),
) -> MessageResponse:
    preference = db.get(UserPreference, _unsubscribe_subject(token))
    if preference is not None:
        preference.email_digest_enabled = False
        preference.updated_at = utcnow()
        db.commit()
    return MessageResponse(message="Email watchlist updates have been disabled.")


def _unsubscribe_subject(token: str) -> str:
    secret = link_signing_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="Email links are not configured.")
    try:
        payload = jwt.decode(token, secret, algorithms=[LINK_SIGNING_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail=_INVALID_UNSUBSCRIBE_DETAIL) from exc
    subject = payload.get("sub")
    if payload.get("purpose") != _UNSUBSCRIBE_PURPOSE or not isinstance(subject, str):
        raise HTTPException(status_code=400, detail=_INVALID_UNSUBSCRIBE_DETAIL)
    return subject
