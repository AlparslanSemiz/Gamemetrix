from __future__ import annotations

import base64
import json
import logging
import re
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..account_security import (
    OAUTH_COOKIE,
    AccountPrincipal,
    clear_account_cookies,
    create_account_session,
    hash_password,
    hash_secret,
    normalize_email,
    optional_account_principal,
    password_needs_rehash,
    require_account_enabled,
    require_account_principal,
    require_csrf,
    require_same_origin,
    revoke_user_sessions,
    set_account_cookies,
    utcnow,
    verify_password,
)
from ..config import get_settings
from ..database import get_db
from ..models import (
    AccountToken,
    AnalyticsEvent,
    Game,
    OAuthIdentity,
    User,
    UserAlertState,
    UserCollection,
    UserPreference,
    VisitEvent,
)
from ..rate_limit import limiter
from ..services.account_email import email_delivery_ready, send_account_email


log = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/account",
    tags=["account"],
    dependencies=[Depends(require_account_enabled)],
)

CollectionType = Literal["watchlist", "playing", "seen", "completed", "liked", "favorites"]
AlertStateType = Literal["read", "dismissed"]
COLLECTION_TYPES: tuple[CollectionType, ...] = (
    "watchlist", "playing", "seen", "completed", "liked", "favorites"
)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESERVED_SETTING_KEYS = frozenset({"guest_state_merged", "gm_guest_state_merged"})


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    message: str


class RegisterPayload(StrictPayload):
    display_name: str = Field(min_length=2, max_length=80)
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Display name must contain at least two visible characters.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value != value.strip() or len(set(value)) < 4:
            raise ValueError("Choose a less repetitive password without leading or trailing spaces.")
        return value


class LoginPayload(StrictPayload):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TokenPayload(StrictPayload):
    token: str = Field(min_length=32, max_length=256)


class ResetPasswordPayload(TokenPayload):
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return RegisterPayload.validate_password(value)


class ForgotPasswordPayload(StrictPayload):
    email: EmailStr = Field(max_length=320)


class CollectionsPayload(StrictPayload):
    watchlist: list[str] = Field(default_factory=list, max_length=5000)
    playing: list[str] = Field(default_factory=list, max_length=5000)
    seen: list[str] = Field(default_factory=list, max_length=5000)
    completed: list[str] = Field(default_factory=list, max_length=5000)
    liked: list[str] = Field(default_factory=list, max_length=5000)
    favorites: list[str] = Field(default_factory=list, max_length=5000)


class PreferencePayload(StrictPayload):
    min_discount: int = Field(default=20, ge=1, le=90)
    min_score: int = Field(default=80, ge=1, le=100)
    upcoming_days: int = Field(default=45, ge=1, le=365)
    email_digest_enabled: bool = False
    marketing_enabled: bool = False
    settings: dict = Field(default_factory=dict)


class MergePayload(StrictPayload):
    collections: CollectionsPayload = Field(default_factory=CollectionsPayload)
    preferences: PreferencePayload = Field(default_factory=PreferencePayload)
    read_alerts: list[str] = Field(default_factory=list, max_length=5000)
    dismissed_alerts: list[str] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def validate_total_collection_size(self) -> "MergePayload":
        total = sum(len(getattr(self.collections, key)) for key in COLLECTION_TYPES)
        if total > 10_000:
            raise ValueError("Combined collection payload is too large.")
        return self


class PreferencePatch(StrictPayload):
    min_discount: int | None = Field(default=None, ge=1, le=90)
    min_score: int | None = Field(default=None, ge=1, le=100)
    upcoming_days: int | None = Field(default=None, ge=1, le=365)
    email_digest_enabled: bool | None = None
    marketing_enabled: bool | None = None
    settings: dict | None = None


class AlertStatePayload(StrictPayload):
    state: AlertStateType


class AlertStateBulkPayload(AlertStatePayload):
    keys: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("keys")
    @classmethod
    def validate_keys(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value for value in values if value and len(value) <= 240))
        if not cleaned:
            raise ValueError("At least one valid alert key is required.")
        return cleaned


class DeleteAccountPayload(StrictPayload):
    confirmation: Literal["DELETE"]
    current_password: str | None = Field(default=None, max_length=128)


def _account_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "email_verified": user.email_verified_at is not None,
        "created_at": user.created_at.isoformat(),
    }


def _new_account_token(db: Session, user: User, purpose: str, hours: int) -> str:
    now = utcnow()
    for old in db.scalars(
        select(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
        )
    ).all():
        old.consumed_at = now
    raw = token_urlsafe(48)
    db.add(
        AccountToken(
            id=str(uuid4()),
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_secret(raw),
            created_at=now,
            expires_at=now + timedelta(hours=hours),
            consumed_at=None,
        )
    )
    db.commit()
    return raw


def _consume_account_token(db: Session, raw: str, purpose: str) -> User:
    row = db.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == hash_secret(raw),
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
        ).with_for_update()
    )
    if row is None or row.expires_at.replace(tzinfo=row.expires_at.tzinfo or utcnow().tzinfo) <= utcnow():
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    user = db.scalar(select(User).where(User.id == row.user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    row.consumed_at = utcnow()
    return user


async def _send_verification(db: Session, user: User) -> None:
    raw = _new_account_token(db, user, "verify_email", 24)
    link = f"{get_settings().ACCOUNT_BASE_URL}/verify-email?token={raw}"
    await send_account_email(
        user.email,
        "Verify your GameMetrix account",
        f"Welcome to GameMetrix. Verify your email using this link:\n\n{link}\n\nThis link expires in 24 hours.",
    )


def _preference(db: Session, user_id: str) -> UserPreference:
    value = db.get(UserPreference, user_id)
    if value is None:
        value = UserPreference(
            user_id=user_id,
            alert_min_discount=20,
            alert_min_score=80,
            alert_upcoming_days=45,
            email_digest_enabled=False,
            marketing_enabled=False,
            settings={},
            updated_at=utcnow(),
        )
        db.add(value)
        db.flush()
    return value


def _state_payload(db: Session, user: User) -> dict:
    collections: dict[str, list[str]] = {key: [] for key in COLLECTION_TYPES}
    rows = db.execute(
        select(UserCollection.collection_type, Game.slug)
        .join(Game, Game.id == UserCollection.game_id)
        .where(UserCollection.user_id == user.id)
        .order_by(UserCollection.created_at)
    ).all()
    for collection_type, slug in rows:
        if collection_type in collections:
            collections[collection_type].append(slug)

    pref = _preference(db, user.id)
    alert_rows = db.scalars(
        select(UserAlertState).where(UserAlertState.user_id == user.id)
    ).all()
    db.commit()
    return {
        "account": _account_payload(user),
        "collections": collections,
        "preferences": {
            "min_discount": pref.alert_min_discount,
            "min_score": pref.alert_min_score,
            "upcoming_days": pref.alert_upcoming_days,
            "email_digest_enabled": pref.email_digest_enabled,
            "marketing_enabled": pref.marketing_enabled,
            "settings": {
                key: value
                for key, value in (pref.settings or {}).items()
                if key not in _RESERVED_SETTING_KEYS
            },
        },
        "read_alerts": [row.alert_key for row in alert_rows if row.state == "read"],
        "dismissed_alerts": [row.alert_key for row in alert_rows if row.state == "dismissed"],
    }


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def register(request: Request, payload: RegisterPayload, db: Session = Depends(get_db)) -> MessageResponse:
    require_same_origin(request)
    if not email_delivery_ready():
        raise HTTPException(status_code=503, detail="Account email delivery is not configured.")
    email = normalize_email(str(payload.email))
    candidate_password_hash = hash_password(payload.password)
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.email_verified_at is None and existing.is_active:
            try:
                await _send_verification(db, existing)
            except Exception:
                log.exception("Could not resend account verification")
        return MessageResponse(message="Check your email to continue.")
    email_name = email.split("@", 1)[0]
    if len(email_name) >= 3 and email_name in payload.password.casefold():
        raise HTTPException(status_code=422, detail="Password must not contain your email name.")

    now = utcnow()
    user = User(
        id=str(uuid4()),
        email=email,
        display_name=" ".join(payload.display_name.split()),
        password_hash=candidate_password_hash,
        email_verified_at=None,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    db.add(user)
    _preference(db, user.id)
    db.commit()
    try:
        await _send_verification(db, user)
    except Exception as exc:
        log.exception("Could not send account verification")
        raise HTTPException(status_code=503, detail="Verification email could not be sent. Try again shortly.") from exc
    return MessageResponse(message="Check your email to continue.")


@router.post("/email/verify", response_model=MessageResponse)
@limiter.limit("10/minute")
def verify_email(request: Request, payload: TokenPayload, db: Session = Depends(get_db)) -> MessageResponse:
    require_same_origin(request)
    user = _consume_account_token(db, payload.token, "verify_email")
    user.email_verified_at = utcnow()
    user.updated_at = utcnow()
    db.commit()
    return MessageResponse(message="Email verified. You can now log in.")


@router.post("/login")
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
def login(request: Request, response: Response, payload: LoginPayload, db: Session = Depends(get_db)) -> dict:
    require_same_origin(request)
    user = db.scalar(select(User).where(User.email == normalize_email(str(payload.email))))
    password_matches = verify_password(payload.password, user.password_hash if user else None)
    if user is None or not user.is_active or not password_matches:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Verify your email before logging in.")
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    session_token, csrf_token = create_account_session(db, user, request)
    set_account_cookies(response, session_token, csrf_token)
    return {"account": _account_payload(user)}


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
    return {"account": _account_payload(principal.user)}


@router.get("/session")
def account_session(
    principal: AccountPrincipal | None = Depends(optional_account_principal),
) -> dict:
    return {"account": _account_payload(principal.user) if principal else None}


@router.post("/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def forgot_password(request: Request, payload: ForgotPasswordPayload, db: Session = Depends(get_db)) -> MessageResponse:
    require_same_origin(request)
    user = db.scalar(select(User).where(User.email == normalize_email(str(payload.email)), User.is_active.is_(True)))
    if user is not None and user.password_hash and email_delivery_ready():
        raw = _new_account_token(db, user, "reset_password", 1)
        link = f"{get_settings().ACCOUNT_BASE_URL}/reset-password?token={raw}"
        try:
            await send_account_email(
                user.email,
                "Reset your GameMetrix password",
                f"Reset your password using this link:\n\n{link}\n\nThis link expires in one hour.",
            )
        except Exception:
            log.exception("Could not send password reset email")
    return MessageResponse(message="If that account exists, a reset email has been sent.")


@router.post("/password/reset", response_model=MessageResponse)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
def reset_password(request: Request, response: Response, payload: ResetPasswordPayload, db: Session = Depends(get_db)) -> MessageResponse:
    require_same_origin(request)
    user = _consume_account_token(db, payload.token, "reset_password")
    email_name = user.email.split("@", 1)[0]
    if len(email_name) >= 3 and email_name in payload.password.casefold():
        raise HTTPException(status_code=422, detail="Password must not contain your email name.")
    user.password_hash = hash_password(payload.password)
    user.email_verified_at = user.email_verified_at or utcnow()
    user.updated_at = utcnow()
    revoke_user_sessions(db, user.id)
    db.commit()
    clear_account_cookies(response)
    return MessageResponse(message="Password reset. Log in with your new password.")


def _oauth_secret() -> str:
    value = get_settings().JWT_SECRET_KEY
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="Google login is not configured.")
    return value


def _safe_return_to(value: str | None) -> str:
    if not value or len(value) > 300 or "\\" in value or any(ord(char) < 32 for char in value):
        return "/account"
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return "/account"
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


@router.get("/oauth/google/start")
@limiter.limit("20/minute")
def google_start(
    request: Request,
    return_to: str | None = Query(default=None, max_length=300),
) -> RedirectResponse:
    cfg = get_settings()
    if not cfg.GOOGLE_CLIENT_ID or not cfg.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google login is not configured.")
    state = token_urlsafe(32)
    verifier = token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    payload = {
        "purpose": "google_oauth",
        "state": state,
        "verifier": verifier,
        "return_to": _safe_return_to(return_to),
        "exp": utcnow() + timedelta(minutes=10),
    }
    oauth_cookie = jwt.encode(payload, _oauth_secret(), algorithm="HS256")
    params = {
        "client_id": cfg.GOOGLE_CLIENT_ID,
        "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}", status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        oauth_cookie,
        max_age=600,
        httponly=True,
        secure=cfg.is_production,
        samesite="lax",
        path="/api/account/oauth/google",
    )
    return response


@router.get("/email/unsubscribe", response_model=MessageResponse)
@limiter.limit("20/minute")
def unsubscribe_email_digest(
    request: Request,
    token: str = Query(..., min_length=32, max_length=1024),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        payload = jwt.decode(token, _oauth_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail="Unsubscribe link is invalid or expired.") from exc
    if payload.get("purpose") != "unsubscribe_digest" or not isinstance(payload.get("sub"), str):
        raise HTTPException(status_code=400, detail="Unsubscribe link is invalid or expired.")
    pref = db.get(UserPreference, payload["sub"])
    if pref is not None:
        pref.email_digest_enabled = False
        pref.updated_at = utcnow()
        db.commit()
    return MessageResponse(message="Email watchlist updates have been disabled.")


@router.get("/oauth/google/callback")
# Each call makes two outbound HTTPS requests to Google, so it must be bounded.
@limiter.limit("20/minute")
async def google_callback(
    request: Request,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cfg = get_settings()
    if error or not code or not state:
        return RedirectResponse(f"{cfg.ACCOUNT_BASE_URL}/login?oauth=cancelled", status_code=302)
    encoded = request.cookies.get(OAUTH_COOKIE, "")
    try:
        oauth = jwt.decode(
            encoded,
            _oauth_secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "purpose", "state", "verifier"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail="Google login state expired.") from exc
    if (
        oauth.get("purpose") != "google_oauth"
        or oauth.get("state") != state
        or not isinstance(oauth.get("verifier"), str)
    ):
        raise HTTPException(status_code=400, detail="Google login state is invalid.")

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": cfg.GOOGLE_CLIENT_ID,
                "client_secret": cfg.GOOGLE_CLIENT_SECRET,
                "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": oauth["verifier"],
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Google login could not be completed.")
        access_token = token_response.json().get("access_token")
        userinfo_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Google profile could not be read.")
        userinfo = userinfo_response.json()

    subject = str(userinfo.get("sub") or "")
    email = normalize_email(str(userinfo.get("email") or ""))
    display_name = " ".join(str(userinfo.get("name") or email.split("@", 1)[0]).split())[:80]
    if not subject or len(subject) > 255 or not email or len(email) > 320 or not display_name or userinfo.get("email_verified") is not True:
        raise HTTPException(status_code=400, detail="Google did not return a verified email.")
    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == "google",
            OAuthIdentity.provider_subject == subject,
        )
    )
    user = db.get(User, identity.user_id) if identity else db.scalar(select(User).where(User.email == email))
    created_account = user is None
    now = utcnow()
    if user is None:
        user = User(
            id=str(uuid4()),
            email=email,
            display_name=display_name,
            password_hash=None,
            email_verified_at=now,
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=None,
        )
        db.add(user)
        _preference(db, user.id)
        db.flush()
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    user.email_verified_at = user.email_verified_at or now
    if identity is None:
        db.add(
            OAuthIdentity(
                id=str(uuid4()),
                user_id=user.id,
                provider="google",
                provider_subject=subject,
                created_at=now,
            )
        )
    db.commit()
    session_token, csrf_token = create_account_session(db, user, request)
    return_to = _safe_return_to(str(oauth.get("return_to") or "/account"))
    return_parts = urlsplit(return_to)
    return_query = dict(parse_qsl(return_parts.query, keep_blank_values=True))
    return_query["account_event"] = "signup_completed" if created_account else "login_completed"
    return_to = urlunsplit(("", "", return_parts.path, urlencode(return_query), ""))
    response = RedirectResponse(f"{cfg.ACCOUNT_BASE_URL}{return_to}", status_code=302)
    set_account_cookies(response, session_token, csrf_token)
    response.delete_cookie(OAUTH_COOKIE, path="/api/account/oauth/google")
    return response


@router.get("/state")
def account_state(
    principal: AccountPrincipal = Depends(require_account_principal),
    db: Session = Depends(get_db),
) -> dict:
    return _state_payload(db, principal.user)


def _valid_slugs(values: list[str]) -> set[str]:
    return {value for value in values if len(value) <= 180 and _SLUG_RE.fullmatch(value)}


@router.post("/state/merge")
def merge_account_state(
    payload: MergePayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    all_slugs = set().union(*(_valid_slugs(getattr(payload.collections, key)) for key in COLLECTION_TYPES))
    games = {game.slug: game for game in db.scalars(select(Game).where(Game.slug.in_(all_slugs))).all()} if all_slugs else {}
    existing = {
        (row.game_id, row.collection_type)
        for row in db.scalars(select(UserCollection).where(UserCollection.user_id == principal.user.id)).all()
    }
    now = utcnow()
    for collection_type in COLLECTION_TYPES:
        for slug in _valid_slugs(getattr(payload.collections, collection_type)):
            game = games.get(slug)
            if game and (game.id, collection_type) not in existing:
                db.add(
                    UserCollection(
                        user_id=principal.user.id,
                        game_id=game.id,
                        collection_type=collection_type,
                        created_at=now,
                    )
                )
                existing.add((game.id, collection_type))

    pref = _preference(db, principal.user.id)
    settings = dict(pref.settings or {})
    if not (settings.get("gm_guest_state_merged") or settings.get("guest_state_merged")):
        pref.alert_min_discount = payload.preferences.min_discount
        pref.alert_min_score = payload.preferences.min_score
        pref.alert_upcoming_days = payload.preferences.upcoming_days
        pref.email_digest_enabled = payload.preferences.email_digest_enabled
        pref.marketing_enabled = payload.preferences.marketing_enabled
        if len(json.dumps(payload.preferences.settings)) <= 10_000:
            settings.update({
                key: value
                for key, value in payload.preferences.settings.items()
                if key not in _RESERVED_SETTING_KEYS
            })
        settings.pop("guest_state_merged", None)
        settings["gm_guest_state_merged"] = True
        pref.settings = settings
        pref.updated_at = now

    current_alerts = {
        row.alert_key: row
        for row in db.scalars(select(UserAlertState).where(UserAlertState.user_id == principal.user.id)).all()
    }
    incoming_alert_keys = {
        key
        for keys in (payload.read_alerts, payload.dismissed_alerts)
        for key in keys
        if key and len(key) <= 240
    }
    if len(current_alerts) + len(incoming_alert_keys - set(current_alerts)) > 10_000:
        raise HTTPException(status_code=422, detail="Account alert history limit reached.")
    for state_name, keys in (("read", payload.read_alerts), ("dismissed", payload.dismissed_alerts)):
        for key in set(keys):
            if not key or len(key) > 240:
                continue
            row = current_alerts.get(key)
            if row is None:
                row = UserAlertState(user_id=principal.user.id, alert_key=key, state=state_name, updated_at=now)
                db.add(row)
                current_alerts[key] = row
            elif state_name == "dismissed" or row.state != "dismissed":
                row.state = state_name
                row.updated_at = now
    db.commit()
    return _state_payload(db, principal.user)


@router.put("/collections/{collection_type}/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def add_collection_item(
    collection_type: CollectionType,
    slug: str = Path(..., min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    exists_row = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == principal.user.id,
            UserCollection.game_id == game.id,
            UserCollection.collection_type == collection_type,
        )
    )
    if exists_row is None:
        db.add(UserCollection(user_id=principal.user.id, game_id=game.id, collection_type=collection_type, created_at=utcnow()))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/collections/{collection_type}/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_item(
    collection_type: CollectionType,
    slug: str = Path(..., min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    db.execute(
        delete(UserCollection).where(
            UserCollection.user_id == principal.user.id,
            UserCollection.collection_type == collection_type,
            UserCollection.game_id == select(Game.id).where(Game.slug == slug).scalar_subquery(),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/preferences")
def update_preferences(
    payload: PreferencePatch,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    pref = _preference(db, principal.user.id)
    if payload.min_discount is not None:
        pref.alert_min_discount = payload.min_discount
    if payload.min_score is not None:
        pref.alert_min_score = payload.min_score
    if payload.upcoming_days is not None:
        pref.alert_upcoming_days = payload.upcoming_days
    if payload.email_digest_enabled is not None:
        pref.email_digest_enabled = payload.email_digest_enabled
    if payload.marketing_enabled is not None:
        pref.marketing_enabled = payload.marketing_enabled
    if payload.settings is not None:
        if len(json.dumps(payload.settings)) > 10_000:
            raise HTTPException(status_code=422, detail="Settings payload is too large.")
        merged = dict(pref.settings or {})
        merged.update({
            key: value
            for key, value in payload.settings.items()
            if key not in _RESERVED_SETTING_KEYS
        })
        pref.settings = merged
    pref.updated_at = utcnow()
    db.commit()
    return _state_payload(db, principal.user)["preferences"]


@router.put("/alert-state", status_code=status.HTTP_204_NO_CONTENT)
def update_alert_states(
    payload: AlertStateBulkPayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    rows = {
        row.alert_key: row
        for row in db.scalars(
            select(UserAlertState).where(
                UserAlertState.user_id == principal.user.id,
                UserAlertState.alert_key.in_(payload.keys),
            )
        ).all()
    }
    existing_count = db.scalar(
        select(func.count(UserAlertState.id)).where(UserAlertState.user_id == principal.user.id)
    ) or 0
    if existing_count + len(set(payload.keys) - set(rows)) > 10_000:
        raise HTTPException(status_code=422, detail="Account alert history limit reached.")
    now = utcnow()
    for key in payload.keys:
        row = rows.get(key)
        if row is None:
            db.add(UserAlertState(
                user_id=principal.user.id,
                alert_key=key,
                state=payload.state,
                updated_at=now,
            ))
        else:
            row.state = payload.state
            row.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/alert-state/{alert_key}", status_code=status.HTTP_204_NO_CONTENT)
def update_alert_state(
    payload: AlertStatePayload,
    alert_key: str = Path(..., min_length=1, max_length=240),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalar(
        select(UserAlertState).where(
            UserAlertState.user_id == principal.user.id,
            UserAlertState.alert_key == alert_key,
        )
    )
    if row is None:
        count = db.scalar(
            select(func.count(UserAlertState.id)).where(UserAlertState.user_id == principal.user.id)
        ) or 0
        if count >= 10_000:
            raise HTTPException(status_code=422, detail="Account alert history limit reached.")
        db.add(UserAlertState(user_id=principal.user.id, alert_key=alert_key, state=payload.state, updated_at=utcnow()))
    else:
        row.state = payload.state
        row.updated_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export")
def export_account(
    principal: AccountPrincipal = Depends(require_account_principal),
    db: Session = Depends(get_db),
) -> dict:
    return {"exported_at": utcnow().isoformat(), **_state_payload(db, principal.user)}


@router.delete("")
def delete_account(
    response: Response,
    payload: DeleteAccountPayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> MessageResponse:
    if principal.user.password_hash and not verify_password(payload.current_password or "", principal.user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.user_id == principal.user.id))
    db.execute(delete(VisitEvent).where(VisitEvent.user_id == principal.user.id))
    db.delete(principal.user)
    db.commit()
    clear_account_cookies(response)
    return MessageResponse(message="Account deleted.")
