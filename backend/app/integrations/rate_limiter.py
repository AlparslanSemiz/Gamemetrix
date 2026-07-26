"""Persistent provider request and token budgets across daily, monthly, and short windows."""

import asyncio
import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..config import METERED_SOURCES, get_settings

if TYPE_CHECKING:
    from ..models import ApiRequestBudget


log = logging.getLogger(__name__)

_FALLBACK_DAILY_LIMIT = 100


@dataclass(frozen=True)
class WindowSpec:
    kind: str
    seconds: int
    limit: int
    anchor_day: int = 1


class RateLimiter:
    def __init__(self) -> None:
        cfg = get_settings()
        self._limits: dict[str, int] = dict(cfg.provider_daily_limits())
        self._token_limits: dict[str, int] = dict(cfg.provider_daily_token_limits())
        self._aliases: dict[str, str] = dict(cfg.provider_budget_aliases())
        self._window_limits: dict[str, list[WindowSpec]] = {}
        for source, specs in cfg.provider_window_limits().items():
            for kind, limit, seconds in specs:
                self.set_window_limit(
                    source,
                    kind,
                    limit,
                    seconds,
                    anchor_day=cfg.provider_window_reset_day(source, kind),
                )
        self._locks: dict[str, asyncio.Lock] = {}
        self._blocked_until: dict[str, datetime] = {}

    def set_limit(self, source: str, daily_limit: int) -> None:
        self._limits[source] = max(0, int(daily_limit))

    def set_token_limit(self, source: str, daily_tokens: int) -> None:
        self._token_limits[source] = max(0, int(daily_tokens))

    def block(self, source: str, seconds: int) -> None:
        """Temporarily stop a provider without corrupting its configured limit."""
        canonical = self._canonical(source)
        until = datetime.now(UTC).timestamp() + max(1, int(seconds))
        self._blocked_until[canonical] = datetime.fromtimestamp(until, tz=UTC)

    def _blocked(self, source: str) -> bool:
        canonical = self._canonical(source)
        until = self._blocked_until.get(canonical)
        if until is None:
            return False
        if until <= datetime.now(UTC):
            self._blocked_until.pop(canonical, None)
            return False
        return True

    def set_window_limit(
        self,
        source: str,
        kind: str,
        request_limit: int,
        seconds: int,
        *,
        anchor_day: int = 1,
    ) -> None:
        if kind not in {"monthly", "rolling"}:
            raise ValueError("window kind must be monthly or rolling")
        canonical = self._canonical(source)
        specs = [spec for spec in self._window_limits.get(canonical, []) if spec.kind != kind]
        specs.append(
            WindowSpec(
                kind=kind,
                seconds=max(1, seconds),
                limit=max(0, request_limit),
                anchor_day=max(1, min(28, anchor_day)),
            )
        )
        self._window_limits[canonical] = specs

    def share_budget(self, source: str, target: str) -> None:
        self._aliases[source] = target

    def _canonical(self, source: str) -> str:
        return self._aliases.get(source, source)

    def _limit(self, source: str) -> int:
        canonical = self._canonical(source)
        return self._limits.get(canonical, _FALLBACK_DAILY_LIMIT)

    def _token_limit(self, source: str) -> int:
        """0 = this source has no token ceiling, only a request ceiling."""
        return self._token_limits.get(self._canonical(source), 0)

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
        token_limit = self._token_limit(canonical)
        now = datetime.now(UTC)
        if row is None:
            row = ApiRequestBudget(
                source=canonical,
                bucket_date=today,
                request_count=0,
                daily_limit=limit,
                token_count=0,
                token_limit=token_limit,
                updated_at=now,
            )
            db.add(row)
            db.flush()
        elif row.daily_limit != limit or row.token_limit != token_limit:
            row.daily_limit = limit
            row.token_limit = token_limit
            row.updated_at = now
        return row

    @staticmethod
    def _window_start(spec: WindowSpec, now: datetime) -> datetime:
        if spec.kind == "monthly":
            day = min(spec.anchor_day, calendar.monthrange(now.year, now.month)[1])
            current_start = datetime(now.year, now.month, day, tzinfo=UTC)
            if now >= current_start:
                return current_start
            previous_year = now.year if now.month > 1 else now.year - 1
            previous_month = now.month - 1 if now.month > 1 else 12
            previous_day = min(
                spec.anchor_day,
                calendar.monthrange(previous_year, previous_month)[1],
            )
            return datetime(previous_year, previous_month, previous_day, tzinfo=UTC)
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

    async def acquire(self, source: str, estimated_tokens: int = 0) -> bool:
        """Claim one request slot, plus a token reservation for LLM providers.

        The reservation is the caller's worst case. Settle it against the real
        usage with `settle_tokens` once the provider reports it — reserving the
        worst case first is what keeps a burst of concurrent calls from
        overshooting the daily token ceiling.
        """
        if self._blocked(source):
            return False
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
                reservation = max(0, int(estimated_tokens))
                if daily.token_limit and (
                    daily.token_count + reservation
                    > self._effective_limit(source, daily.token_limit)
                ):
                    db.commit()
                    log.debug("Daily token budget exhausted for %s", source)
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
                daily.token_count += reservation
                daily.updated_at = now
                for _, row in windows:
                    row.request_count += 1
                    row.updated_at = now
                db.commit()
                return True

    def settle_tokens(self, source: str, reserved: int, actual: int) -> None:
        """Replace a reservation with what the provider actually charged.

        Best-effort: an accounting failure must never take down the caller.
        Callers must settle to zero only for a definite no-charge rejection.
        Ambiguous timeout, network, server, or malformed-response outcomes keep
        the reservation so provider usage cannot be under-counted.
        """
        delta = max(0, int(actual)) - max(0, int(reserved))
        if not delta:
            return
        from ..database import SessionLocal

        try:
            with SessionLocal() as db:
                self._lock_database_budget(db, source)
                daily = self._get_or_create_daily(db, source)
                daily.token_count = max(0, daily.token_count + delta)
                daily.updated_at = datetime.now(UTC)
                db.commit()
        except Exception:
            log.debug("Token settlement failed for %s", source, exc_info=True)

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
            # A token-limited source with no tokens left can serve no request,
            # whatever its request counter says.
            starved = bool(daily.token_limit) and self._tokens_remaining(source, daily) <= 0
            db.commit()
            if self._blocked(source) or starved:
                return 0
            return max(0, min(remaining_values))

    def _tokens_remaining(self, source: str, daily: "ApiRequestBudget") -> int:
        return max(0, self._effective_limit(source, daily.token_limit) - daily.token_count)

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
                tokens_left = self._tokens_remaining(source, daily) if daily.token_limit else None
                output[source] = {
                    "remaining": (
                        0
                        if self._blocked(source) or tokens_left == 0
                        else max(0, min(remaining_values))
                    ),
                    "limit": daily.daily_limit,
                    "usable_limit": usable_daily,
                    "used": daily.request_count,
                    "token_limit": daily.token_limit or None,
                    "token_usable_limit": (
                        self._effective_limit(source, daily.token_limit)
                        if daily.token_limit
                        else None
                    ),
                    "tokens_used": daily.token_count if daily.token_limit else None,
                    "tokens_remaining": tokens_left,
                    "reserve_percent": get_settings().budget_reserve_percent(self._canonical(source)),
                    "metered": self._canonical(source) in METERED_SOURCES,
                    "updated_at": daily.updated_at.isoformat() if daily.updated_at else None,
                    "windows": window_output,
                    "blocked_until": (
                        self._blocked_until[self._canonical(source)].isoformat()
                        if self._blocked(source)
                        else None
                    ),
                }
            db.commit()
        return output


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
