from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from typing import Literal


SourceStatus = Literal["live", "mock", "unavailable"]
HealthStatus = Literal[
    "ok",
    "failing",
    "missing",
    "disabled",
    "invalid_key",
    "rate_limited",
    "provider_error",
    "timeout",
]


PlayerMode = Literal["singleplayer", "multiplayer", "coop"]

# Provider mode/tag labels → the three canonical modes the catalog filters on.
# IGDB uses game_modes.name; RAWG exposes the same signal through tags.
_PLAYER_MODE_BY_LABEL: dict[str, PlayerMode] = {
    "single player": "singleplayer",
    "singleplayer": "singleplayer",
    "single-player": "singleplayer",
    "multiplayer": "multiplayer",
    "multi player": "multiplayer",
    "multi-player": "multiplayer",
    "massively multiplayer online (mmo)": "multiplayer",
    "massively multiplayer": "multiplayer",
    "mmo": "multiplayer",
    "mmorpg": "multiplayer",
    "battle royale": "multiplayer",
    "pvp": "multiplayer",
    "co-operative": "coop",
    "cooperative": "coop",
    "co-op": "coop",
    "coop": "coop",
    "online co-op": "coop",
    "local co-op": "coop",
    "split screen": "coop",
    "split-screen": "coop",
}


def normalize_game_modes(labels: list[str]) -> list[PlayerMode]:
    """Map provider mode/tag labels onto the canonical player modes, de-duplicated."""
    modes: list[PlayerMode] = []
    for label in labels:
        if not isinstance(label, str):
            continue
        mode = _PLAYER_MODE_BY_LABEL.get(label.strip().lower())
        if mode and mode not in modes:
            modes.append(mode)
    return modes


def bounded_float(
    value: object,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float | None:
    """Parse an untrusted provider number and reject non-finite/out-of-range values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed) or parsed < minimum or (maximum is not None and parsed > maximum):
        return None
    return parsed


def bounded_int(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = 2_000_000_000,
) -> int | None:
    """Parse an integral provider value without silently truncating decimals."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed_float = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed_float) or not parsed_float.is_integer():
        return None
    parsed = int(parsed_float)
    if not minimum <= parsed <= maximum:
        return None
    return parsed


@dataclass(frozen=True)
class ExternalScore:
    source: str
    score: float
    scale: int = 100
    status: SourceStatus = "live"
    detail: str | None = None
    review_count: int = 0
    raw: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or len(self.source) > 60:
            raise ValueError("External score source must be 1-60 characters.")
        if self.status not in {"live", "mock", "unavailable"}:
            raise ValueError("External score status is invalid.")
        if not isinstance(self.scale, int) or not 1 <= self.scale <= 100:
            raise ValueError("External score scale must be between 1 and 100.")
        numeric_score = float(self.score)
        if not isfinite(numeric_score) or not 0 <= numeric_score <= self.scale:
            raise ValueError("External score is outside its declared scale.")
        if not isinstance(self.review_count, int) or not 0 <= self.review_count <= 2_000_000_000:
            raise ValueError("External score review count is invalid.")
        if self.raw is not None and not isinstance(self.raw, dict):
            raise ValueError("External score raw payload must be an object.")


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
    game_modes: list[str] = field(default_factory=list)
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

    def __post_init__(self) -> None:
        if self.score is not None and bounded_float(self.score, maximum=100.0) is None:
            raise ValueError("Normalized game score must be between 0 and 100.")
        if self.score_count is not None and bounded_int(self.score_count) is None:
            raise ValueError("Normalized game score count is invalid.")
        for price in (self.list_price, self.sale_price):
            if price is not None and bounded_float(price, maximum=1_000_000.0) is None:
                raise ValueError("Normalized game price is invalid.")
        if not isinstance(self.raw, dict):
            raise ValueError("Normalized game raw payload must be an object.")


@dataclass
class SourceHealth:
    """Masked health status for one API source. Never contains keys or secrets."""

    source: str
    configured: bool
    working: bool
    status: HealthStatus
    message: str | None = None
    latency_ms: int | None = None
