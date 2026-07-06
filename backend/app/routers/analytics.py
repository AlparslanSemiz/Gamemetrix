from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import VisitEvent
from ..rate_limit import limiter


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class PageViewPayload(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    visitor_id: str | None = Field(default=None, max_length=128)
    referrer: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    screen_width: int | None = Field(default=None, ge=0, le=10000)
    screen_height: int | None = Field(default=None, ge=0, le=10000)


def _stable_hash(value: str | None) -> str | None:
    if not value:
        return None
    salt = get_settings().JWT_SECRET_KEY or "gamemetrix-development-analytics-salt"
    return sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def _client_ip(request: Request) -> str | None:
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        raw = request.headers.get(header)
        if raw:
            return raw.split(",", 1)[0].strip()[:128]
    return request.client.host[:128] if request.client else None


def _clean_path(path: str) -> str:
    value = path.strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        value = parsed.path or "/"
        if parsed.query:
            value = f"{value}?{parsed.query}"
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
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:500]
    visitor_source = payload.visitor_id or f"{ip or 'unknown'}:{user_agent or 'unknown'}"

    db.add(
        VisitEvent(
            visitor_id_hash=_stable_hash(visitor_source) or "",
            ip_hash=_stable_hash(ip),
            user_agent_hash=_stable_hash(user_agent),
            path=_clean_path(payload.path),
            referrer=payload.referrer,
            title=payload.title,
            screen_width=payload.screen_width,
            screen_height=payload.screen_height,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
