"""Persistent provider request budgets across daily, monthly, and short windows."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ..config import METERED_SOURCES, get_settings


log = logging.getLogger(__name__)

_FALLBACK_DAILY_LIMIT = 100


@dataclass(frozen=True)
class WindowSpec:
    kind: str
    seconds: int
    limit: int


class RateLimiter:
    def __init__(self) -> None:
        cfg = get_settings()
        self._limits: dict[str, int] = dict(cfg.provider_daily_limits())
        self._aliases: dict[str, str] = dict(cfg.provider_budget_aliases())
        self._window_limits: dict[str, list[WindowSpec]] = {}
        for source, specs in cfg.provider_window_limits().items():
            for kind, limit, seconds in specs:
                self.set_window_limit(source, kind, limit, seconds)
        self._locks: dict[str, asyncio.Lock] = {}

    def set_limit(self, source: str, daily_limit: int) -> None:
        self._limits[source] = max(0, int(daily_limit))

    def set_window_limit(self, source: str, kind: str, request_limit: int, seconds: int) -> None:
        if kind not in {"monthly", "rolling"}:
            raise ValueError("window kind must be monthly or rolling")
        canonical = self._canonical(source)
        specs = [spec for spec in self._window_limits.get(canonical, []) if spec.kind != kind]
        specs.append(WindowSpec(kind=kind, seconds=max(1, seconds), limit=max(0, request_limit)))
        self._window_limits[canonical] = specs

    def share_budget(self, source: str, target: str) -> None:
        self._aliases[source] = target

    def _canonical(self, source: str) -> str:
        return self._aliases.get(source, source)

    def _limit(self, source: str) -> int:
        canonical = self._canonical(source)
        return self._limits.get(canonical, _FALLBACK_DAILY_LIMIT)

    def _effective_limit(self, source: str, value: int) -> int:
        """Usable slots after the safety reserve — metered providers reserve more."""
        reserve = get_settings().budget_reserve_percent(self._canonical(source))
        return max(0, value * (100 - reserve) // 100)

    def _lock(self, source: str) -> asyncio.Lock:
        canonical = self._canonical(source)
        if canonical not in self._locks:
            self._locks[canonical] = asyncio.Lock()
        return self._locks[canonical]

    def _lock_database_budget(self, db, source: str) -> None:
        from sqlalchemy import func, select

        canonical = self._canonical(source)
        db.execute(select(func.pg_advisory_xact_lock(func.hashtext(canonical))))

    def _get_or_create_daily(self, db, source: str):
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

    @staticmethod
    def _window_start(spec: WindowSpec, now: datetime) -> datetime:
        if spec.kind == "monthly":
            return datetime(now.year, now.month, 1, tzinfo=UTC)
        epoch = int(now.timestamp())
        return datetime.fromtimestamp(epoch - (epoch % spec.seconds), tz=UTC)

    def _get_window_rows(self, db, source: str):
        from sqlalchemy import select

        from ..models import ApiRequestWindow

        canonical = self._canonical(source)
        now = datetime.now(UTC)
        rows = []
        for spec in self._window_limits.get(canonical, []):
            start = self._window_start(spec, now)
            row = db.scalar(
                select(ApiRequestWindow).where(
                    ApiRequestWindow.source == canonical,
                    ApiRequestWindow.window_kind == spec.kind,
                    ApiRequestWindow.window_start == start,
                )
            )
            if row is None:
                row = ApiRequestWindow(
                    source=canonical,
                    window_kind=spec.kind,
                    window_start=start,
                    window_seconds=spec.seconds,
                    request_count=0,
                    request_limit=spec.limit,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
            elif row.request_limit != spec.limit or row.window_seconds != spec.seconds:
                row.request_limit = spec.limit
                row.window_seconds = spec.seconds
                row.updated_at = now
            rows.append((spec, row))
        return rows

    async def acquire(self, source: str) -> bool:
        async with self._lock(source):
            from ..database import SessionLocal

            with SessionLocal() as db:
                self._lock_database_budget(db, source)
                daily = self._get_or_create_daily(db, source)
                windows = self._get_window_rows(db, source)
                if daily.request_count >= self._effective_limit(source, daily.daily_limit):
                    db.commit()
                    log.debug("Daily request budget exhausted for %s", source)
                    return False
                if any(
                    row.request_count >= self._effective_limit(source, row.request_limit)
                    for _, row in windows
                ):
                    db.commit()
                    log.debug("Provider request window exhausted for %s", source)
                    return False
                now = datetime.now(UTC)
                daily.request_count += 1
                daily.updated_at = now
                for _, row in windows:
                    row.request_count += 1
                    row.updated_at = now
                db.commit()
                return True

    def remaining(self, source: str) -> int:
        from ..database import SessionLocal

        with SessionLocal() as db:
            self._lock_database_budget(db, source)
            daily = self._get_or_create_daily(db, source)
            remaining_values = [self._effective_limit(source, daily.daily_limit) - daily.request_count]
            remaining_values.extend(
                self._effective_limit(source, row.request_limit) - row.request_count
                for _, row in self._get_window_rows(db, source)
            )
            db.commit()
            return max(0, min(remaining_values))

    def status(self) -> dict[str, dict[str, object]]:
        from ..database import SessionLocal

        all_sources = set(self._limits) | set(self._aliases)
        output: dict[str, dict[str, object]] = {}
        with SessionLocal() as db:
            for source in sorted(all_sources):
                self._lock_database_budget(db, source)
                daily = self._get_or_create_daily(db, source)
                window_output = {}
                usable_daily = self._effective_limit(source, daily.daily_limit)
                remaining_values = [usable_daily - daily.request_count]
                for spec, row in self._get_window_rows(db, source):
                    usable_window = self._effective_limit(source, row.request_limit)
                    remaining = max(0, usable_window - row.request_count)
                    remaining_values.append(remaining)
                    window_output[spec.kind] = {
                        "remaining": remaining,
                        "limit": row.request_limit,
                        "usable_limit": usable_window,
                        "used": row.request_count,
                        "window_start": row.window_start.isoformat(),
                        "window_seconds": row.window_seconds,
                    }
                output[source] = {
                    "remaining": max(0, min(remaining_values)),
                    "limit": daily.daily_limit,
                    "usable_limit": usable_daily,
                    "used": daily.request_count,
                    "reserve_percent": get_settings().budget_reserve_percent(self._canonical(source)),
                    "metered": self._canonical(source) in METERED_SOURCES,
                    "updated_at": daily.updated_at.isoformat() if daily.updated_at else None,
                    "windows": window_output,
                }
            db.commit()
        return output


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
