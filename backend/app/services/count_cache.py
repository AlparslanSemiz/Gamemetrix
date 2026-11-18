"""Short-lived cache for catalog COUNT(*) results.

Paging through one filter set re-ran the same full-catalog COUNT on every page. The total
only changes when the catalog does, so a few minutes of staleness is invisible to users.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Sequence

COUNT_CACHE_TTL_SECONDS = 300.0
COUNT_CACHE_MAX_ENTRIES = 256
# Parameters that change which rows come back but never how many match.
_NON_COUNT_PARAMS = frozenset({"sort", "direction", "limit", "offset"})

_cache: OrderedDict[tuple, tuple[float, int]] = OrderedDict()


def count_cache_key(namespace: str, params: Sequence[tuple[str, str]]) -> tuple:
    kept = tuple(sorted((k, v) for k, v in params if k not in _NON_COUNT_PARAMS))
    return (namespace, kept)


def cached_count(
    key: tuple,
    compute: Callable[[], int],
    *,
    now: Callable[[], float] = time.monotonic,
) -> int:
    current = now()
    hit = _cache.get(key)
    if hit is not None and current - hit[0] < COUNT_CACHE_TTL_SECONDS:
        _cache.move_to_end(key)
        return hit[1]
    value = int(compute())
    _cache[key] = (current, value)
    _cache.move_to_end(key)
    while len(_cache) > COUNT_CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)
    return value


def clear_count_cache() -> None:
    _cache.clear()

