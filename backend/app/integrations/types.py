from dataclasses import dataclass
from typing import Literal


SourceStatus = Literal["live", "mock", "unavailable"]


@dataclass(frozen=True)
class ExternalScore:
    source: str
    score: float
    scale: int = 100
    status: SourceStatus = "live"
    detail: str | None = None
    review_count: int = 0
