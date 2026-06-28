"""Per-source daily API request budget.

Prevents blowing through external API rate limits when batch-refreshing games.
Budgets reset at midnight local time. Configure via environment variables or
`RateLimiter.set_limit()` at startup.

Free-tier defaults (override in .env):
  OpenCritic / RapidAPI free:  100 req/month  → 4/day  (OPENCRITIC_DAILY_LIMIT)
  IGDB:                        4 req/s burst   → 400/day (IGDB_DAILY_LIMIT)
  RAWG:                        20 k req/month  → 600/day (RAWG_DAILY_LIMIT)
  Steam Store:                 unofficial cap  → 300/day (STEAM_DAILY_LIMIT)
  SteamSpy:                    no stated limit → 300/day (STEAMSPY_DAILY_LIMIT)
"""
import asyncio
import logging
from datetime import date

log = logging.getLogger(__name__)

_DEFAULT_DAILY_LIMITS: dict[str, int] = {
    "Metacritic": 600,
    "OpenCritic": 4,
    "IGDB": 400,
    "Steam": 300,
    "SteamSpy": 300,
    "RAWG": 600,
    "CheapShark": 200,
    "FreeToGame": 200,
}


class _SourceBudget:
    __slots__ = ("_limit", "_count", "_date", "_lock")

    def __init__(self, daily_limit: int) -> None:
        self._limit = daily_limit
        self._count = 0
        self._date: date = date.today()
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if today != self._date:
            self._count = 0
            self._date = today

    async def acquire(self) -> bool:
        async with self._get_lock():
            self._reset_if_new_day()
            if self._count >= self._limit:
                return False
            self._count += 1
            return True

    def remaining(self) -> int:
        self._reset_if_new_day()
        return max(0, self._limit - self._count)

    @property
    def limit(self) -> int:
        return self._limit


class RateLimiter:
    def __init__(self) -> None:
        self._budgets: dict[str, _SourceBudget] = {}

    def set_limit(self, source: str, daily_limit: int) -> None:
        self._budgets[source] = _SourceBudget(daily_limit)

    def _budget(self, source: str) -> _SourceBudget:
        if source not in self._budgets:
            self._budgets[source] = _SourceBudget(_DEFAULT_DAILY_LIMITS.get(source, 100))
        return self._budgets[source]

    async def acquire(self, source: str) -> bool:
        """Claim one request slot. Returns False when today's budget is exhausted."""
        granted = await self._budget(source).acquire()
        if not granted:
            log.debug("Rate budget exhausted for %s today", source)
        return granted

    def remaining(self, source: str) -> int:
        return self._budget(source).remaining()

    def status(self) -> dict[str, dict[str, int]]:
        all_sources = set(_DEFAULT_DAILY_LIMITS) | set(self._budgets)
        return {
            src: {
                "remaining": self._budget(src).remaining(),
                "limit": self._budget(src).limit,
            }
            for src in sorted(all_sources)
        }


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
