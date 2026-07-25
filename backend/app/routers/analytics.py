import re
from datetime import UTC, datetime
from hashlib import sha256
from ipaddress import ip_address
from math import isfinite
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from ..config import get_settings
from ..account_security import AccountPrincipal, optional_account_principal, require_same_origin
from ..database import get_db
from ..models import AnalyticsEvent, VisitEvent
from ..rate_limit import limiter


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class PageViewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=500)
    visitor_id: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    referrer: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    screen_width: int | None = Field(default=None, ge=0, le=10000)
    screen_height: int | None = Field(default=None, ge=0, le=10000)
    session_id: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    language: str | None = Field(default=None, max_length=35, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    timezone: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*$")


AnalyticsEventType = Literal[
    "signup_completed",
    "login_completed",
    "wishlist_add",
    "alert_enabled",
    "store_outbound",
    "share",
]

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STORE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&'_+-]{0,79}$")
_BOT_USER_AGENT_RE = re.compile(
    r"(?:bot\b|crawler|spider|headlesschrome|lighthouse|pagespeed|"
    r"pingdom|uptime|curl/|wget/|python-requests|httpx/|playwright|selenium)",
    re.IGNORECASE,
)
_EVENT_PROPERTIES: dict[str, frozenset[str]] = {
    "signup_completed": frozenset({"method"}),
    "login_completed": frozenset({"method"}),
    "wishlist_add": frozenset({"game_slug"}),
    "alert_enabled": frozenset({"kind"}),
    "store_outbound": frozenset({"game_slug", "store"}),
    "share": frozenset({"game_slug", "surface"}),
}


class AnalyticsEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: AnalyticsEventType
    visitor_id: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    path: str | None = Field(default=None, max_length=500)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_properties(self) -> "AnalyticsEventPayload":
        if len(self.properties) > 10:
            raise ValueError("Too many analytics properties.")
        for key, value in self.properties.items():
            if not key or len(key) > 64:
                raise ValueError("Analytics property keys must be 1-64 characters.")
            if isinstance(value, str) and len(value) > 200:
                raise ValueError("Analytics string properties must be at most 200 characters.")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("Analytics number properties must be finite.")
        required = _EVENT_PROPERTIES[self.event_type]
        if set(self.properties) != required:
            raise ValueError(f"{self.event_type} requires exactly: {', '.join(sorted(required))}.")
        values = self.properties
        if self.event_type in {"signup_completed", "login_completed"} and values["method"] not in {"password", "google"}:
            raise ValueError("Unknown account authentication method.")
        if "game_slug" in values and (
            not isinstance(values["game_slug"], str) or not _SLUG_RE.fullmatch(values["game_slug"])
        ):
            raise ValueError("Invalid analytics game slug.")
        if self.event_type == "alert_enabled" and values["kind"] not in {"daily_digest", "deal", "free", "release", "score"}:
            raise ValueError("Unknown alert kind.")
        if self.event_type == "store_outbound" and (
            not isinstance(values["store"], str) or not _STORE_RE.fullmatch(values["store"])
        ):
            raise ValueError("Invalid analytics store name.")
        if self.event_type == "share" and values["surface"] not in {"game_card", "game_detail", "curation"}:
            raise ValueError("Unknown share surface.")
        return self


def _stable_hash(value: str | None) -> str | None:
    if not value:
        return None
    return sha256(f"{get_settings().analytics_salt()}:{value}".encode("utf-8")).hexdigest()


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",", 1)[0].strip()
    try:
        return ip_address(candidate).compressed
    except ValueError:
        return None


def _client_ip(request: Request) -> str | None:
    """
    Resolved peer address.

    Reads only request.client: uvicorn (--proxy-headers --forwarded-allow-ips)
    has already applied the forwarded headers when the peer is a trusted proxy,
    and nginx only honours CF-Connecting-IP from Cloudflare's ranges. Trusting
    the raw headers here would let any caller forge the address stored against
    every visit.
    """
    return _valid_ip(request.client.host if request.client else None)


def _country_code(request: Request) -> str | None:
    if not get_settings().ANALYTICS_TRUST_PROXY_HEADERS:
        return None
    value = request.headers.get("cf-ipcountry", "").strip().upper()
    return value if len(value) == 2 and value.isalpha() else None


def _looks_like_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(_BOT_USER_AGENT_RE.search(user_agent))


def _clean_path(path: str) -> str:
    value = path.strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        value = parsed.path or "/"
    else:
        value = value.split("?", 1)[0]
    value = value.split("#", 1)[0]
    if not value.startswith("/"):
        value = f"/{value}"
    return value[:500]


def _clean_referrer(referrer: str | None) -> str | None:
    if not referrer:
        return None
    parsed = urlparse(referrer.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    if ":" in host:
        host = f"[{host}]"
    if port:
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}{parsed.path or '/'}"[:500]


@router.post("/page-view", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("120/minute")
def record_page_view(
    request: Request,
    payload: PageViewPayload,
    db: Session = Depends(get_db),
    principal: AccountPrincipal | None = Depends(optional_account_principal),
    _origin: None = Depends(require_same_origin),
) -> Response:
    cfg = get_settings()
    now = datetime.now(UTC)
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:500]
    if _looks_like_bot(user_agent):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    visitor_source = payload.visitor_id or f"{ip or 'unknown'}:{user_agent or 'unknown'}"

    # Retention is enforced by services.background.raw_analytics_retention_loop,
    # not here: a sweep that only runs inside this handler would stop the moment
    # traffic stops, and would never purge anything once raw-IP storage is
    # switched off — leaving already-stored addresses in place indefinitely.
    db.add(
        VisitEvent(
            user_id=principal.user.id if principal else None,
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
            referrer=_clean_referrer(payload.referrer),
            title=payload.title,
            screen_width=payload.screen_width,
            screen_height=payload.screen_height,
            created_at=now,
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/event", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("120/minute")
def record_event(
    request: Request,
    payload: AnalyticsEventPayload,
    db: Session = Depends(get_db),
    principal: AccountPrincipal | None = Depends(optional_account_principal),
    _origin: None = Depends(require_same_origin),
) -> Response:
    if _looks_like_bot(request.headers.get("user-agent")):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    allowed = _EVENT_PROPERTIES[payload.event_type]
    properties = {
        key: value
        for key, value in payload.properties.items()
        if key in allowed and len(str(value)) <= 180
    }
    db.add(
        AnalyticsEvent(
            event_type=payload.event_type,
            visitor_id_hash=_stable_hash(payload.visitor_id),
            user_id=principal.user.id if principal else None,
            path=_clean_path(payload.path) if payload.path else None,
            properties=properties,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
