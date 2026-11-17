"""Per-account login failure limit.

The per-IP limit stops one client hammering the endpoint, but an attacker with many
addresses can still grind one account's password. This tracks failed logins per
normalized e-mail (known or not, so it reveals nothing about which accounts exist) and
answers 429 once an address has collected too many failures in a window.

State is in process memory: production runs a single uvicorn worker (see the Dockerfile
CMD), so one process sees every attempt. A restart forgets the counters, which only
ever loosens the limit back to the per-IP one.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque

from fastapi import HTTPException

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60
MAX_TRACKED_ACCOUNTS = 10_000

_failures: OrderedDict[str, deque[float]] = OrderedDict()


def _recent(key: str, now: float) -> deque[float]:
    attempts = _failures.get(key)
    if attempts is None:
        return deque()
    while attempts and now - attempts[0] >= WINDOW_SECONDS:
        attempts.popleft()
    if not attempts:
        del _failures[key]
    return attempts


def ensure_login_allowed(email: str, *, now: float | None = None) -> None:
    """Raise 429 (with Retry-After) when this account has too many recent failures."""
    current = time.monotonic() if now is None else now
    attempts = _recent(email, current)
    if len(attempts) >= MAX_FAILURES:
        retry_after = max(1, int(WINDOW_SECONDS - (current - attempts[0])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def record_login_failure(email: str, *, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    attempts = _recent(email, current)
    attempts.append(current)
    _failures[email] = attempts
    _failures.move_to_end(email)
    while len(_failures) > MAX_TRACKED_ACCOUNTS:
        _failures.popitem(last=False)


def clear_login_failures(email: str) -> None:
    _failures.pop(email, None)
