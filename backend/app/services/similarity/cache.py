"""
In-process cache for related-game lookups.

Similarity ranking scans a large candidate pool and scores it in pure Python, so
an uncached endpoint recomputes the same answer on every visit. Results are
memoised per (slug, limit) and concurrent lookups for the same key are coalesced
onto a single task, mirroring `services/trailer_cache.py`.

Only slugs are cached — ORM instances would outlive their session. Callers
re-select the winners in their own session.

Public API:
  cached_similar_slugs(slug, limit) -> list[str]
  cached_series_slugs(slug, limit)  -> list[str]
  clear_similarity_cache()          -> None
"""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ...database import SessionLocal
from ...models import Game
from .queries import find_series_games, find_similar_games

_CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_MAX_SIZE = 2000

_CacheKey = tuple[str, int]

_similar_entries: OrderedDict[_CacheKey, tuple[float, list[str]]] = OrderedDict()
_series_entries: OrderedDict[_CacheKey, tuple[float, list[str]]] = OrderedDict()
_inflight: dict[tuple[str, _CacheKey], asyncio.Task[list[str]]] = {}
_cache_lock = asyncio.Lock()


async def cached_similar_slugs(slug: str, limit: int) -> list[str]:
    return await _cached_slugs("similar", _similar_entries, slug, limit, _compute_similar)


async def cached_series_slugs(slug: str, limit: int) -> list[str]:
    return await _cached_slugs("series", _series_entries, slug, limit, _compute_series)


def clear_similarity_cache() -> None:
    _similar_entries.clear()
    _series_entries.clear()


def _compute_similar(db: Session, source: Game, limit: int) -> list[str]:
    return [game.slug for game in find_similar_games(db, source, display_limit=limit)]


def _compute_series(db: Session, source: Game, limit: int) -> list[str]:
    return [game.slug for game in find_series_games(db, source, limit=limit)]


async def _cached_slugs(
    namespace: str,
    entries: OrderedDict[_CacheKey, tuple[float, list[str]]],
    slug: str,
    limit: int,
    compute: Callable[[Session, Game, int], list[str]],
) -> list[str]:
    key = (slug, limit)
    now = time.monotonic()
    async with _cache_lock:
        cached = entries.get(key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            entries.move_to_end(key)
            return cached[1]
        task = _inflight.get((namespace, key))
        if task is None:
            task = asyncio.create_task(_lookup_and_cache(namespace, entries, key, compute))
            _inflight[(namespace, key)] = task
    return await asyncio.shield(task)


async def _lookup_and_cache(
    namespace: str,
    entries: OrderedDict[_CacheKey, tuple[float, list[str]]],
    key: _CacheKey,
    compute: Callable[[Session, Game, int], list[str]],
) -> list[str]:
    try:
        slugs = await run_in_threadpool(_compute_in_session, key, compute)
        async with _cache_lock:
            entries[key] = (time.monotonic(), slugs)
            entries.move_to_end(key)
            while len(entries) > _CACHE_MAX_SIZE:
                entries.popitem(last=False)
        return slugs
    finally:
        current = asyncio.current_task()
        async with _cache_lock:
            if _inflight.get((namespace, key)) is current:
                _inflight.pop((namespace, key), None)


def _compute_in_session(
    key: _CacheKey,
    compute: Callable[[Session, Game, int], list[str]],
) -> list[str]:
    """Own session so the result never depends on a request's session lifetime."""
    slug, limit = key
    with SessionLocal() as db:
        source = db.scalar(select(Game).where(Game.slug == slug))
        if source is None:
            return []
        return compute(db, source, limit)
