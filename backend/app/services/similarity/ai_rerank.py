"""Optional Groq re-rank of the heuristic "games like X" candidates.

The heuristic ranker (ranking.py) stays authoritative and always runs first.
When SIMILARITY_USE_AI is on and Groq is configured, Groq reorders the top
heuristic candidates into the best `limit`. Any failure falls back to the
heuristic order. This never touches any score — it orders display only.
"""

import logging
import re

from ...config import get_settings
from ...integrations.groq import generate_text
from ...models import Game

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You recommend video games similar to a reference game. You are given the "
    "reference game and a numbered list of candidate games. Return only the "
    "numbers of the best matches, most similar first, comma-separated "
    "(for example: 3, 1, 5). Judge similarity by genre, gameplay style, theme, "
    "and mood. Do not add any text besides the numbers."
)


def _describe(game: Game) -> str:
    genres = ", ".join(game.genres or []) or "unknown"
    return f"{game.title} — {genres}"


def _parse_order(answer: str, count: int) -> list[int]:
    ordered: list[int] = []
    for match in re.findall(r"\d+", answer):
        index = int(match)
        if 1 <= index <= count and index not in ordered:
            ordered.append(index)
    return ordered


async def rerank_with_ai(source: Game, ranked: list[Game], limit: int) -> list[Game]:
    """Reorder the heuristic candidates via Groq, or return them unchanged."""
    cfg = get_settings()
    if not (cfg.SIMILARITY_USE_AI and cfg.groq_configured()):
        return ranked[:limit]

    pool = ranked[: max(limit, cfg.SIMILARITY_AI_POOL)]
    if len(pool) <= 1:
        return pool[:limit]

    prompt = (
        f"Reference game: {_describe(source)}\n\nCandidates:\n"
        + "\n".join(f"{i}. {_describe(game)}" for i, game in enumerate(pool, start=1))
    )
    answer = await generate_text(_SYSTEM_PROMPT, prompt)
    if not answer:
        return pool[:limit]

    order = _parse_order(answer, len(pool))
    if not order:
        return pool[:limit]

    chosen = [pool[index - 1] for index in order]
    chosen_slugs = {game.slug for game in chosen}
    remainder = [game for game in pool if game.slug not in chosen_slugs]
    return (chosen + remainder)[:limit]
