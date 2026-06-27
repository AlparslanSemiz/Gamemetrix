from dataclasses import dataclass, field
from datetime import date
from typing import Literal


SourceStatus = Literal["live", "mock", "unavailable"]
HealthStatus = Literal["ok", "failing", "missing", "disabled"]


@dataclass(frozen=True)
class ExternalScore:
    source: str
    score: float
    scale: int = 100
    status: SourceStatus = "live"
    detail: str | None = None
    review_count: int = 0
    raw: dict[str, str | float | int] | None = None


@dataclass
class NormalizedGame:
    """
    Canonical intermediate representation returned by every service adapter.
    Raw API responses are NEVER written directly to DB — they go through this first.
    """

    source: str
    external_id: str
    name: str
    external_slug: str | None = None
    external_url: str | None = None
    release_date: date | None = None
    platforms: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    developer: str | None = None
    publisher: str | None = None
    summary: str | None = None
    cover_url: str | None = None
    # Score (0-100 scale)
    score: float | None = None
    score_count: int | None = None
    is_critic_score: bool = False
    # Pricing (optional, price-type sources only)
    list_price: float | None = None
    sale_price: float | None = None
    currency: str = "USD"
    # Raw payload kept for audit/debug
    raw: dict = field(default_factory=dict)


@dataclass
class SourceHealth:
    """Masked health status for one API source. Never contains keys or secrets."""

    source: str
    configured: bool
    working: bool
    status: HealthStatus
    message: str | None = None
    latency_ms: int | None = None
