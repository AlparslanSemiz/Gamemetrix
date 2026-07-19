from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import VisitEvent
from ..rate_limit import limiter


router = APIRouter(prefix="/api/analytics", tags=["analytics"])
_last_raw_data_cleanup: datetime | None = None


class PageViewPayload(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    visitor_id: str | None = Field(default=None, max_length=128)
    referrer: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    screen_width: int | None = Field(default=None, ge=0, le=10000)
    screen_height: int | None = Field(default=None, ge=0, le=10000)
    session_id: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=35)
    timezone: str | None = Field(default=None, max_length=64)


def _stable_hash(value: str | None) -> str | None:
    if not value:
        return None
    salt = get_settings().JWT_SECRET_KEY or "gamemetrix-development-analytics-salt"
    return sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",", 1)[0].strip()
    try:
        return ip_address(candidate).compressed
    except ValueError:
        return None


def _client_ip(request: Request) -> str | None:
    if get_settings().ANALYTICS_TRUST_PROXY_HEADERS:
        # Prefer headers that the bundled nginx proxy always overwrites.
        for header in ("x-real-ip", "x-forwarded-for", "cf-connecting-ip"):
            parsed = _valid_ip(request.headers.get(header))
            if parsed:
                return parsed
    return _valid_ip(request.client.host if request.client else None)


def _country_code(request: Request) -> str | None:
    if not get_settings().ANALYTICS_TRUST_PROXY_HEADERS:
        return None
    value = request.headers.get("cf-ipcountry", "").strip().upper()
    return value if len(value) == 2 and value.isalpha() else None


def _clean_path(path: str) -> str:
    value = path.strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        value = parsed.path or "/"
    else:
        value = value.split("?", 1)[0]
    if not value.startswith("/"):
        value = f"/{value}"
    return value[:500]


@router.post("/page-view", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("120/minute")
def record_page_view(
    request: Request,
    payload: PageViewPayload,
    db: Session = Depends(get_db),
) -> Response:
    global _last_raw_data_cleanup

    cfg = get_settings()
    now = datetime.now(UTC)
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:500]
    visitor_source = payload.visitor_id or f"{ip or 'unknown'}:{user_agent or 'unknown'}"

    # Raw network data is optional and automatically redacted after the
    # configured retention window. Stable hashes remain for aggregate counts.
    cleanup_due = (
        _last_raw_data_cleanup is None
        or now - _last_raw_data_cleanup >= timedelta(hours=24)
    )
    if cfg.ANALYTICS_STORE_RAW_IP and cleanup_due:
        cutoff = now - timedelta(days=cfg.ANALYTICS_RAW_IP_RETENTION_DAYS)
        db.execute(
            update(VisitEvent)
            .where(VisitEvent.created_at < cutoff, VisitEvent.ip_address.is_not(None))
            .values(ip_address=None, user_agent=None)
        )
        _last_raw_data_cleanup = now

    db.add(
        VisitEvent(
            visitor_id_hash=_stable_hash(visitor_source) or "",
            session_id_hash=_stable_hash(payload.session_id),
            ip_hash=_stable_hash(ip),
            ip_address=ip if cfg.ANALYTICS_STORE_RAW_IP else None,
            country_code=_country_code(request),
            user_agent_hash=_stable_hash(user_agent),
            user_agent=user_agent if cfg.ANALYTICS_STORE_RAW_IP else None,
            language=payload.language,
            timezone=payload.timezone,
            path=_clean_path(payload.path),
            referrer=payload.referrer,
            title=payload.title,
            screen_width=payload.screen_width,
            screen_height=payload.screen_height,
            created_at=now,
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
