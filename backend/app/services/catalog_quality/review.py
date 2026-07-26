"""Structured AI prompt and strict response parsing for catalog quality."""

import json
import logging
from dataclasses import dataclass

from ...integrations.ai import generate_text
from ...models import Game

log = logging.getLogger(__name__)

_ALLOWED_VERDICTS = frozenset({"OK", "NOT_GAME", "BAD_METADATA"})
_ALLOWED_FIELDS = frozenset(
    {"title", "summary", "release_year", "genres", "platforms", "developer", "publisher", "content_type"}
)
_MAX_PROMPT_SUMMARY_CHARS = 900
_MAX_REASON_CHARS = 500
_MAX_DUPLICATE_TITLES = 8
_AI_MAX_OUTPUT_TOKENS = 220
_AI_TEMPERATURE = 0.0

_QUALITY_PROMPT = (
    "You audit one video-game catalog row. Judge only the supplied row. "
    "BAD_METADATA means the title is junk/placeholder, the description clearly belongs "
    "to another title, or a supplied fact is clearly malformed or contradictory. "
    "NOT_GAME means the row is not a standalone playable game (for example DLC, "
    "soundtrack, tool, asset pack, demo, or dedicated server). Missing optional data "
    "alone is not bad metadata. Return only compact JSON with keys verdict, fields, "
    "and reason. verdict must be OK, NOT_GAME, or BAD_METADATA. fields must be an "
    "array chosen from title, summary, release_year, genres, platforms, developer, "
    "publisher, content_type."
)


@dataclass(frozen=True)
class QualityVerdict:
    verdict: str
    fields: tuple[str, ...]
    reason: str


def parse_quality_verdict(answer: str | None) -> QualityVerdict | None:
    if not answer:
        return None
    start = answer.find("{")
    end = answer.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(answer[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    verdict = str(payload.get("verdict") or "").strip().upper()
    if verdict not in _ALLOWED_VERDICTS:
        return None
    raw_fields = payload.get("fields")
    fields = tuple(
        dict.fromkeys(
            str(field).strip().casefold()
            for field in raw_fields
            if isinstance(field, str) and str(field).strip().casefold() in _ALLOWED_FIELDS
        )
    ) if isinstance(raw_fields, list) else ()
    reason = str(payload.get("reason") or "").strip()[:_MAX_REASON_CHARS]
    return QualityVerdict(verdict=verdict, fields=fields, reason=reason)


async def ai_review(
    game: Game,
    signals: list[str],
    duplicate_titles: tuple[str, ...],
) -> QualityVerdict | None:
    prompt = _quality_record_prompt(game, signals, duplicate_titles)
    answer = await generate_text(
        _QUALITY_PROMPT,
        prompt,
        max_output_tokens=_AI_MAX_OUTPUT_TOKENS,
        temperature=_AI_TEMPERATURE,
        json_object=True,
        response_validator=_valid_quality_response,
    )
    verdict = parse_quality_verdict(answer)
    if answer and verdict is None:
        log.debug("AI catalog-quality response was not valid JSON")
    return verdict


def _quality_record_prompt(
    game: Game,
    signals: list[str],
    duplicate_titles: tuple[str, ...],
) -> str:
    scores = [
        {
            "source": score.get("source"),
            "score": score.get("score"),
            "review_count": score.get("review_count", 0),
        }
        for score in game.source_scores or []
        if isinstance(score, dict)
    ]
    row = {
        "title": game.title,
        "summary": (game.summary or "")[:_MAX_PROMPT_SUMMARY_CHARS],
        "release_year": game.release_year,
        "genres": game.genres,
        "platforms": game.platforms,
        "developer": game.developer,
        "publisher": game.publisher,
        "content_type": game.content_type,
        "scores": scores,
        "signals": signals,
        "same_summary_other_titles": list(duplicate_titles[:_MAX_DUPLICATE_TITLES]),
    }
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


def _valid_quality_response(answer: str) -> bool:
    return parse_quality_verdict(answer) is not None
