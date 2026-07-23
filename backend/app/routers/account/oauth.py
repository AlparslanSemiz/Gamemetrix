"""Google sign-in: authorization redirect and callback."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...account_security import (
    LINK_SIGNING_ALGORITHM,
    OAUTH_COOKIE,
    create_account_session,
    link_signing_secret,
    set_account_cookies,
    utcnow,
)
from ...config import Settings, get_settings
from ...database import get_db
from ...integrations.google_oauth import (
    GoogleOAuthError,
    PkceChallenge,
    authorization_url,
    fetch_userinfo,
)
from ...rate_limit import limiter
from ...services.google_identity import (
    AccountDisabledError,
    GoogleIdentityError,
    ResolvedAccount,
    resolve_account,
    validated_identity,
)

router = APIRouter(prefix="/oauth/google")

# Each callback makes two outbound HTTPS requests to Google, so it must be bounded.
OAUTH_RATE_LIMIT = "20/minute"

_STATE_TTL_MINUTES = 10
_OAUTH_COOKIE_PATH = "/api/account/oauth/google"
_MAX_RETURN_TO_LENGTH = 300
_DEFAULT_RETURN_TO = "/account"
_OAUTH_PURPOSE = "google_oauth"


def oauth_secret() -> str:
    secret = link_signing_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="Google login is not configured.")
    return secret


def safe_return_to(value: str | None) -> str:
    if (
        not value
        or len(value) > _MAX_RETURN_TO_LENGTH
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        return _DEFAULT_RETURN_TO
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return _DEFAULT_RETURN_TO
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


@router.get("/start")
@limiter.limit(OAUTH_RATE_LIMIT)
def google_start(
    request: Request,
    return_to: str | None = Query(default=None, max_length=_MAX_RETURN_TO_LENGTH),
) -> RedirectResponse:
    cfg = get_settings()
    if not cfg.GOOGLE_CLIENT_ID or not cfg.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google login is not configured.")

    pkce = PkceChallenge.generate()
    response = RedirectResponse(authorization_url(cfg, pkce), status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        _encode_state_cookie(pkce, safe_return_to(return_to)),
        max_age=_STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=cfg.is_production,
        samesite="lax",
        path=_OAUTH_COOKIE_PATH,
    )
    return response


def _encode_state_cookie(pkce: PkceChallenge, return_to: str) -> str:
    return jwt.encode(
        {
            "purpose": _OAUTH_PURPOSE,
            "state": pkce.state,
            "verifier": pkce.verifier,
            "return_to": return_to,
            "exp": utcnow() + timedelta(minutes=_STATE_TTL_MINUTES),
        },
        oauth_secret(),
        algorithm=LINK_SIGNING_ALGORITHM,
    )


def _decode_state_cookie(encoded: str, state: str) -> dict:
    try:
        oauth = jwt.decode(
            encoded,
            oauth_secret(),
            algorithms=[LINK_SIGNING_ALGORITHM],
            options={"require": ["exp", "purpose", "state", "verifier"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=400, detail="Google login state expired.") from exc
    if (
        oauth.get("purpose") != _OAUTH_PURPOSE
        or oauth.get("state") != state
        or not isinstance(oauth.get("verifier"), str)
    ):
        raise HTTPException(status_code=400, detail="Google login state is invalid.")
    return oauth


@router.get("/callback")
@limiter.limit(OAUTH_RATE_LIMIT)
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

    oauth = _decode_state_cookie(request.cookies.get(OAUTH_COOKIE, ""), state)
    account = await _resolve_google_account(db, cfg, code, oauth["verifier"])
    return _login_redirect(db, cfg, oauth, account, request)


async def _resolve_google_account(
    db: Session,
    cfg: Settings,
    code: str,
    verifier: str,
) -> ResolvedAccount:
    try:
        userinfo = await fetch_userinfo(cfg, code, verifier)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        return resolve_account(db, validated_identity(userinfo))
    except GoogleIdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AccountDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _login_redirect(
    db: Session,
    cfg: Settings,
    oauth: dict,
    account: ResolvedAccount,
    request: Request,
) -> RedirectResponse:
    session_token, csrf_token = create_account_session(db, account.user, request)
    return_to = _with_account_event(
        safe_return_to(str(oauth.get("return_to") or _DEFAULT_RETURN_TO)),
        "signup_completed" if account.created else "login_completed",
    )
    response = RedirectResponse(f"{cfg.ACCOUNT_BASE_URL}{return_to}", status_code=302)
    set_account_cookies(response, session_token, csrf_token)
    response.delete_cookie(OAUTH_COOKIE, path=_OAUTH_COOKIE_PATH)
    return response


def _with_account_event(return_to: str, event: str) -> str:
    parts = urlsplit(return_to)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["account_event"] = event
    return urlunsplit(("", "", parts.path, urlencode(query), ""))
