"""Optional AI re-rank of the heuristic "games like X" candidates.

The heuristic ranker (ranking.py) stays authoritative and always runs first.
When SIMILARITY_USE_AI is on and any AI provider is configured, AI reorders the top
heuristic candidates into the best `limit`. Any failure falls back to the
heuristic order. This never touches any score — it orders display only.
"""

import asyncio
import logging
import re
import time

from ...config import get_settings
from ...integrations.ai import generate_text
from ...integrations.rate_limiter import get_rate_limiter
from ...models import Game

log = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 6 * 60 * 60
_MAX_CACHE_ENTRIES = 256
_cache: dict[tuple[object, ...], tuple[float, tuple[str, ...]]] = {}
_rate_lock = asyncio.Lock()
_last_request_started = 0.0

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
    """Reorder the heuristic candidates via AI, or return them unchanged."""
    cfg = get_settings()
    if not (cfg.SIMILARITY_USE_AI and cfg.ai_configured()):
        return ranked[:limit]

    pool = ranked[: max(limit, cfg.SIMILARITY_AI_POOL)]
    if len(pool) <= 1:
        return pool[:limit]

    cache_key = (source.slug, limit, *(game.slug for game in pool))
    cached = _cache_get(cache_key, pool)
    if cached is not None:
        return cached
    if not await get_rate_limiter().acquire("AI:Similarity"):
        return pool[:limit]
    await _wait_for_similarity_slot(cfg.SIMILARITY_AI_MIN_INTERVAL_SECONDS)

    prompt = (
        f"Reference game: {_describe(source)}\n\nCandidates:\n"
        + "\n".join(f"{i}. {_describe(game)}" for i, game in enumerate(pool, start=1))
    )
    answer = await generate_text(
        _SYSTEM_PROMPT,
        prompt,
        max_output_tokens=96,
        deadline_seconds=cfg.AI_INTERACTIVE_DEADLINE_SECONDS,
    )
    if not answer:
        return pool[:limit]

    order = _parse_order(answer, len(pool))
    if not order:
        return pool[:limit]

    chosen = [pool[index - 1] for index in order]
    chosen_slugs = {game.slug for game in chosen}
    remainder = [game for game in pool if game.slug not in chosen_slugs]
    result = (chosen + remainder)[:limit]
    _cache_put(cache_key, result)
    return result


async def _wait_for_similarity_slot(interval_seconds: float) -> None:
    global _last_request_started
    async with _rate_lock:
        wait_seconds = interval_seconds - (time.monotonic() - _last_request_started)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        _last_request_started = time.monotonic()


def _cache_get(
    key: tuple[object, ...],
    pool: list[Game],
) -> list[Game] | None:
    cached = _cache.get(key)
    if cached is None:
        return None
    expires_at, slugs = cached
    if expires_at <= time.monotonic():
        _cache.pop(key, None)
        return None
    by_slug = {game.slug: game for game in pool}
    result = [by_slug[slug] for slug in slugs if slug in by_slug]
    return result if len(result) == len(slugs) else None


def _cache_put(key: tuple[object, ...], games: list[Game]) -> None:
    now = time.monotonic()
    if len(_cache) >= _MAX_CACHE_ENTRIES:
        expired = [cache_key for cache_key, (expiry, _) in _cache.items() if expiry <= now]
        for cache_key in expired:
            _cache.pop(cache_key, None)
        while len(_cache) >= _MAX_CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)))
    _cache[key] = (now + _CACHE_TTL_SECONDS, tuple(game.slug for game in games))
