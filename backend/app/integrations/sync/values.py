"""Reading a score row's numeric fields safely.

`score_value` returns the usable score or None; `review_count` is re-exported
from `game_signals` so the clamping rule lives in exactly one place.
"""

from collections.abc import Mapping
from math import isfinite

from ...game_signals import safe_review_count as review_count

__all__ = ["review_count", "score_value"]

_MIN_SCORE_EXCLUSIVE = 0
_MAX_SCORE = 100


def score_value(row: Mapping[str, object]) -> float | None:
    try:
        value = float(row.get("score", 0) or 0)
    except (TypeError, ValueError):
        return None
    if not isfinite(value) or not _MIN_SCORE_EXCLUSIVE < value <= _MAX_SCORE:
        return None
    return value
