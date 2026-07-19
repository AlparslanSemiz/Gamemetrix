"""Persistent per-source daily API request budget.

Prevents blowing through external API rate limits when batch-refreshing games.
Counters are stored in PostgreSQL, so restarting the backend does not reset
today's budget.
"""
import asyncio
import logging
from datetime import UTC, datetime

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
    "ITAD": 200,
}


class RateLimiter:
    def __init__(self) -> None:
        self._limits: dict[str, int] = dict(_DEFAULT_DAILY_LIMITS)
        self._aliases: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def set_limit(self, source: str, daily_limit: int) -> None:
        self._limits[source] = max(0, int(daily_limit))

    def share_budget(self, source: str, target: str) -> None:
        """Make `source` draw from `target`'s budget — for sources served by the
        same upstream API key (e.g. Metacritic scores come from the RAWG API)."""
        self._aliases[source] = target

    def _canonical(self, source: str) -> str:
        return self._aliases.get(source, source)

    def _limit(self, source: str) -> int:
        return self._limits.get(self._canonical(source), _DEFAULT_DAILY_LIMITS.get(self._canonical(source), 100))

    def _lock(self, source: str) -> asyncio.Lock:
        canonical = self._canonical(source)
        if canonical not in self._locks:
            self._locks[canonical] = asyncio.Lock()
        return self._locks[canonical]

    def _get_or_create_row(self, db, source: str):
        from sqlalchemy import select

        from ..models import ApiRequestBudget

        canonical = self._canonical(source)
        today = datetime.now(UTC).date()
        row = db.scalar(
            select(ApiRequestBudget).where(
                ApiRequestBudget.source == canonical,
                ApiRequestBudget.bucket_date == today,
            )
        )
        limit = self._limit(canonical)
        now = datetime.now(UTC)
        if row is None:
            row = ApiRequestBudget(
                source=canonical,
                bucket_date=today,
                request_count=0,
                daily_limit=limit,
                updated_at=now,
            )
            db.add(row)
            db.flush()
        elif row.daily_limit != limit:
            row.daily_limit = limit
            row.updated_at = now
        return row

    async def acquire(self, source: str) -> bool:
        """Claim one request slot. Returns False when today's budget is exhausted."""
        async with self._lock(source):
            from ..database import SessionLocal

            with SessionLocal() as db:
                row = self._get_or_create_row(db, source)
                if row.request_count >= row.daily_limit:
                    db.commit()
                    log.debug("Rate budget exhausted for %s today", source)
                    return False
                row.request_count += 1
                row.updated_at = datetime.now(UTC)
                db.commit()
                return True

    def remaining(self, source: str) -> int:
        from ..database import SessionLocal

        with SessionLocal() as db:
            row = self._get_or_create_row(db, source)
            remaining = max(0, row.daily_limit - row.request_count)
            db.commit()
            return remaining

    def status(self) -> dict[str, dict[str, int]]:
        from sqlalchemy import select

        from ..database import SessionLocal
        from ..models import ApiRequestBudget

        all_sources = set(_DEFAULT_DAILY_LIMITS) | set(self._limits) | set(self._aliases)
        canonical_sources = {self._canonical(source) for source in all_sources}
        today = datetime.now(UTC).date()
        now = datetime.now(UTC)

        with SessionLocal() as db:
            rows = db.scalars(
                select(ApiRequestBudget).where(
                    ApiRequestBudget.bucket_date == today,
                    ApiRequestBudget.source.in_(canonical_sources),
                )
            ).all()
            by_source = {row.source: row for row in rows}

            for canonical in canonical_sources:
                limit = self._limit(canonical)
                row = by_source.get(canonical)
                if row is None:
                    row = ApiRequestBudget(
                        source=canonical,
                        bucket_date=today,
                        request_count=0,
                        daily_limit=limit,
                        updated_at=now,
                    )
                    db.add(row)
                    db.flush()
                    by_source[canonical] = row
                elif row.daily_limit != limit:
                    row.daily_limit = limit
                    row.updated_at = now

            status = {
                source: {
                    "remaining": max(0, by_source[self._canonical(source)].daily_limit - by_source[self._canonical(source)].request_count),
                    "limit": self._limit(source),
                }
                for source in sorted(all_sources)
            }
            db.commit()
            return status


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
