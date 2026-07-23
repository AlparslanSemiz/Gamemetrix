"""
In-process trailer lookup cache.

YouTube trailer lookups are slow and quota-bound, so results are memoised per
slug and concurrent lookups for the same slug are coalesced onto a single task.

Public API:
  cached_trailer_video_id(slug, title) -> str | None
  clear_trailer_cache()                -> None
"""

import asyncio
import time
from collections import OrderedDict

from ..integrations.youtube import find_trailer_video_id

_CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_MAX_SIZE = 1000
_MAX_CONCURRENT_LOOKUPS = 4

_cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
_inflight: dict[str, asyncio.Task[str | None]] = {}
_cache_lock = asyncio.Lock()
_lookup_slots = asyncio.Semaphore(_MAX_CONCURRENT_LOOKUPS)


async def cached_trailer_video_id(slug: str, title: str) -> str | None:
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(slug)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            _cache.move_to_end(slug)
            return cached[1]
        task = _inflight.get(slug)
        if task is None:
            task = asyncio.create_task(_lookup_and_cache(slug, title))
            _inflight[slug] = task
    return await asyncio.shield(task)


def clear_trailer_cache() -> None:
    _cache.clear()


async def _lookup_and_cache(slug: str, title: str) -> str | None:
    try:
        async with _lookup_slots:
            video_id = await find_trailer_video_id(title)
        async with _cache_lock:
            _cache[slug] = (time.monotonic(), video_id)
            _cache.move_to_end(slug)
            while len(_cache) > _CACHE_MAX_SIZE:
                _cache.popitem(last=False)
        return video_id
    finally:
        current = asyncio.current_task()
        async with _cache_lock:
            if _inflight.get(slug) is current:
                _inflight.pop(slug, None)
