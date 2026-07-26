"""
Admin audit trail — who did what on the admin surface.

Every /admin/* request is recorded (reads included) plus every login attempt,
so an operator can answer "who changed this and when" after the fact.

Public API:
  record_admin_event(...)          -> None
  audit_admin_request(request, call_next) -> Response   (ASGI http middleware)
  recent_admin_audit_logs(db, ...) -> list[AdminAuditLog]
  purge_admin_audit_logs(db, ...)  -> int
"""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode

import jwt
from fastapi import Request
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import AdminAuditLog
from ..rate_limit import get_client_ip


log = logging.getLogger(__name__)

_AUDITED_PATH_PREFIX = "/admin"
_MAX_PATH_LENGTH = 500
_MAX_QUERY_LENGTH = 500
_MAX_USER_AGENT_LENGTH = 300
_MAX_USERNAME_LENGTH = 64
_FAILURE_STATUS_FLOOR = 400
_DEFAULT_AUDIT_PAGE_SIZE = 100
_ANONYMOUS_USERNAME = None
_SENSITIVE_QUERY_PARTS = ("token", "password", "secret", "code", "key", "credential")


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def redact_query(query: str | None) -> str | None:
    if not query:
        return None
    redacted = [
        (
            key,
            "[REDACTED]"
            if any(part in key.casefold() for part in _SENSITIVE_QUERY_PARTS)
            else value,
        )
        for key, value in parse_qsl(query, keep_blank_values=True)
    ]
    return _truncate(urlencode(redacted), _MAX_QUERY_LENGTH)


def _username_from_bearer_token(request: Request) -> str | None:
    """Best-effort identity for logging — never raises, never blocks the request."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    cfg = get_settings()
    try:
        payload = jwt.decode(
            token,
            cfg.JWT_SECRET_KEY,
            algorithms=[cfg.JWT_ALGORITHM],
            issuer=cfg.JWT_ISSUER,
            audience=cfg.JWT_AUDIENCE or None,
            options={"verify_aud": bool(cfg.JWT_AUDIENCE)},
        )
    except jwt.InvalidTokenError:
        # An expired/forged token still deserves an audit row, just without a verified name.
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def record_admin_event(
    *,
    username: str | None,
    action: str,
    method: str,
    path: str,
    status_code: int,
    query: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Persist one audit row in its own session so it survives a failed request transaction."""
    entry = AdminAuditLog(
        username=_truncate(username, _MAX_USERNAME_LENGTH),
        action=action,
        method=method,
        path=_truncate(path, _MAX_PATH_LENGTH) or path[:_MAX_PATH_LENGTH],
        query=redact_query(query),
        status_code=status_code,
        success=status_code < _FAILURE_STATUS_FLOOR,
        ip_address=ip_address,
        user_agent=_truncate(user_agent, _MAX_USER_AGENT_LENGTH),
        duration_ms=duration_ms,
        created_at=datetime.now(UTC),
    )
    try:
        with SessionLocal() as db:
            db.add(entry)
            db.commit()
    except Exception:
        # Auditing must never break the request it is describing.
        log.exception("Failed to write admin audit log for %s %s", method, path)


async def audit_admin_request(request: Request, call_next):
    """HTTP middleware: records every /admin/* request once the response status is known."""
    if not request.url.path.startswith(_AUDITED_PATH_PREFIX):
        return await call_next(request)

    started = datetime.now(UTC)
    response = await call_next(request)
    elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

    record_admin_event(
        username=_username_from_bearer_token(request),
        action="admin_request",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query) or None,
        status_code=response.status_code,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        duration_ms=elapsed_ms,
    )
    return response


def record_login_attempt(request: Request, username: str, status_code: int) -> None:
    record_admin_event(
        username=username or _ANONYMOUS_USERNAME,
        action="login",
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def recent_admin_audit_logs(
    db: Session,
    *,
    limit: int = _DEFAULT_AUDIT_PAGE_SIZE,
    action: str | None = None,
    only_failures: bool = False,
) -> list[AdminAuditLog]:
    query = select(AdminAuditLog)
    if action:
        query = query.where(AdminAuditLog.action == action)
    if only_failures:
        query = query.where(AdminAuditLog.success.is_(False))
    query = query.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id)).limit(limit)
    return list(db.scalars(query).all())


def purge_admin_audit_logs(db: Session, *, older_than_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = db.execute(delete(AdminAuditLog).where(AdminAuditLog.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)
