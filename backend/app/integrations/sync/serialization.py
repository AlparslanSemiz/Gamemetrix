"""Converting ExternalScore objects to stored rows and merging them in."""

from datetime import UTC, datetime

from ..types import ExternalScore
from .constants import SOURCE_ORDER, UNRANKED_SOURCE_ORDER


def score_to_dict(score: ExternalScore) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": score.source,
        "score": score.score,
        "scale": score.scale,
        "status": score.status,
        "review_count": score.review_count,
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    if score.detail:
        payload["detail"] = score.detail
    if score.raw:
        payload.update(score.raw)
    return payload


def merge_source_scores(
    current: list[dict[str, object]],
    fresh: list[ExternalScore],
) -> list[dict[str, object]]:
    """Fresh rows win unless they would replace a live row with a non-live one."""
    by_source = {str(s["source"]): s for s in current}
    for score in fresh:
        existing = by_source.get(score.source)
        existing_status = str(existing.get("status", "")) if existing else ""
        if score.status == "live" or existing is None or existing_status != "live":
            by_source[score.source] = score_to_dict(score)
    return sorted(
        by_source.values(),
        key=lambda s: SOURCE_ORDER.get(str(s.get("source", "")), UNRANKED_SOURCE_ORDER),
    )
