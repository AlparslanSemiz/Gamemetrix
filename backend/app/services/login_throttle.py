"""Failed-login limits per account.

In process memory (production runs one uvicorn worker, so one process sees every attempt; a
restart only loosens this back to the per-IP slowapi limit). Two layers:

* Hard limit per (e-mail, client IP/64) pair: MAX_PAIR_ATTEMPTS in WINDOW_SECONDS, then 429.
  The key includes the client, so someone guessing a victim's address locks out only
  themselves, never the real owner on another network.
* Soft limit per e-mail across all clients: past MAX_EMAIL_ATTEMPTS in the window every
  further attempt is *delayed* (1, 2, 4, 8, at most 15 s) instead of refused. The owner is
  never locked out, but distributed guessing becomes slow. A caller presenting a valid signed
  device cookie for that e-mail (issued on a previous successful login, see
  account_security.device_cookie_valid) skips both layers; the IP is not part of that trust.

Attempts are *reserved* before the password is checked and released only on success, under one
lock, so concurrent requests cannot all pass a check that none has counted yet. The maps never
evict live counters: when they are full and nothing has expired, brand-new keys are simply not
tracked (the per-IP slowapi limit still applies to them).
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException

MAX_PAIR_ATTEMPTS = 10
MAX_EMAIL_ATTEMPTS = 20
WINDOW_SECONDS = 15 * 60
MAX_TRACKED_KEYS = 10_000
MAX_DELAY_SECONDS = 15.0

_lock = threading.Lock()
_pairs: dict[tuple[str, str], deque[float]] = {}
_emails: dict[str, deque[float]] = {}


def reset() -> None:
    with _lock:
        _pairs.clear()
        _emails.clear()


def _trim(attempts: deque[float], now: float) -> None:
    while attempts and now - attempts[0] >= WINDOW_SECONDS:
        attempts.popleft()


def _purge_expired(now: float) -> None:
    for table in (_pairs, _emails):
        for key in [k for k, v in table.items() if not v or now - v[-1] >= WINDOW_SECONDS]:
            del table[key]


def _may_track_new_keys(now: float) -> bool:
    if len(_pairs) + len(_emails) < MAX_TRACKED_KEYS:
        return True
    _purge_expired(now)
    return len(_pairs) + len(_emails) < MAX_TRACKED_KEYS


def reserve_login_attempt(
    email: str,
    client: str,
    *,
    device_trusted: bool = False,
    now: float | None = None,
) -> tuple[float | None, float]:
    """Count this attempt. Returns (reservation token, seconds to delay) or raises 429.

    The token goes to release_login_attempt() on success; it is None when nothing was counted
    (trusted device, or the tables are full of live entries).
    """
    if device_trusted:
        return None, 0.0
    current = time.monotonic() if now is None else now
    pair = (email, client)
    with _lock:
        pair_attempts = _pairs.get(pair)
        email_attempts = _emails.get(email)
        if pair_attempts is not None:
            _trim(pair_attempts, current)
            if len(pair_attempts) >= MAX_PAIR_ATTEMPTS:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Try again later.",
                    headers={
                        "Retry-After": str(int(WINDOW_SECONDS - (current - pair_attempts[0])) + 1)
                    },
                )
        delay = 0.0
        if email_attempts is not None:
            _trim(email_attempts, current)
            excess = len(email_attempts) - MAX_EMAIL_ATTEMPTS
            if excess >= 0:
                delay = min(MAX_DELAY_SECONDS, float(2 ** min(excess, 4)))

        if (pair_attempts is None or email_attempts is None) and not _may_track_new_keys(current):
            return None, delay
        if pair_attempts is None:
            pair_attempts = _pairs.setdefault(pair, deque())
        if email_attempts is None:
            email_attempts = _emails.setdefault(email, deque())
        pair_attempts.append(current)
        email_attempts.append(current)
        return current, delay


def release_login_attempt(email: str, client: str, token: float | None) -> None:
    """Successful login: hand the reservation back."""
    if token is None:
        return
    with _lock:
        for table, key in ((_pairs, (email, client)), (_emails, email)):
            attempts = table.get(key)
            if attempts is None:
                continue
            try:
                attempts.remove(token)
            except ValueError:
                pass
            if not attempts:
                del table[key]
