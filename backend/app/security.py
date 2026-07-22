from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError

from .config import get_settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
_DUMMY_ADMIN_HASH = bcrypt.hashpw(b"GameMetrix timing-only admin sentinel", bcrypt.gensalt())


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _require_jwt_secret() -> str:
    secret = get_settings().JWT_SECRET_KEY
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY must be configured with at least 32 characters.",
        )
    return secret


def verify_admin_password(username: str, password: str) -> bool:
    cfg = get_settings()
    if len(password) > 1024:
        return False
    username_matches = bool(cfg.ADMIN_USERNAME) and compare_digest(username, cfg.ADMIN_USERNAME)
    candidate = cfg.ADMIN_PASSWORD_HASH.encode("utf-8") if username_matches and cfg.ADMIN_PASSWORD_HASH else _DUMMY_ADMIN_HASH
    try:
        password_matches = bcrypt.checkpw(password.encode("utf-8"), candidate)
        return username_matches and bool(cfg.ADMIN_PASSWORD_HASH) and password_matches
    except ValueError:
        return False


def create_access_token(user: AuthenticatedUser) -> str:
    cfg = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=cfg.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user.username,
        "role": user.role,
        "iss": cfg.JWT_ISSUER,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    if cfg.JWT_AUDIENCE:
        payload["aud"] = cfg.JWT_AUDIENCE
    return jwt.encode(payload, _require_jwt_secret(), algorithm=cfg.JWT_ALGORITHM)


def _decode_access_token(token: str) -> AuthenticatedUser:
    cfg = get_settings()
    decode_options: dict[str, Any] = {
        "require": ["exp", "iat", "nbf", "iss", "sub", "role"],
        "verify_aud": bool(cfg.JWT_AUDIENCE),
    }
    decode_kwargs: dict[str, Any] = {
        "algorithms": [cfg.JWT_ALGORITHM],
        "issuer": cfg.JWT_ISSUER,
        "options": decode_options,
    }
    if cfg.JWT_AUDIENCE:
        decode_kwargs["audience"] = cfg.JWT_AUDIENCE

    try:
        payload = jwt.decode(token, _require_jwt_secret(), **decode_kwargs)
    except InvalidTokenError as exc:
        raise _auth_error() from exc

    username = payload.get("sub")
    role = payload.get("role")
    if not isinstance(username, str) or not isinstance(role, str):
        raise _auth_error()
    return AuthenticatedUser(username=username, role=role)


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> AuthenticatedUser:
    if not token:
        if request.cookies.get("gm_session"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Normal accounts cannot access admin endpoints.",
            )
        raise _auth_error()
    return _decode_access_token(token)


def optional_admin_user(
    token: str | None = Depends(oauth2_scheme),
) -> AuthenticatedUser | None:
    if not token:
        return None
    user = _decode_access_token(token)
    return user if user.role == "admin" else None


def require_admin_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return current_user
