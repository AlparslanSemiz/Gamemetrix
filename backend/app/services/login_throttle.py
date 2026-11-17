"""Failed-login limits per account.

Two layers, both in process memory (production runs one uvicorn worker, so one process sees
every attempt; a restart only loosens the limit back to the per-IP slowapi one):

* Hard limit per (e-mail, client IP/64) pair: MAX_PAIR_ATTEMPTS in WINDOW_SECONDS. Because the
  key includes the client, an attacker hammering a victim's address locks out only their own
  pair, never the real owner on a different IP.
* Soft limit per e-mail across all clients: MAX_EMAIL_ATTEMPTS in the window, to slow a
  distributed guess. A pair that has logged in successfully before (and has no failures in
  the window) is exempt, so the owner on their usual network is not locked out by it.

Every attempt is *reserved* before the password is checked and released only on success, under
one lock, so concurrent requests cannot all pass a check that none has counted yet. Map
eviction only drops expired entries; when the maps are full and nothing has expired, new keys
are admitted through a global brake instead of evicting live counters.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException

MAX_PAIR_ATTEMPTS = 10
MAX_EMAIL_ATTEMPTS = 50
WINDOW_SECONDS = 15 * 60
MAX_TRACKED_KEYS = 10_000
TRUSTED_SECONDS = 30 * 24 * 3600
# When the maps are full of live entries: at most this many brand-new keys per minute.
FULL_MAP_NEW_KEYS_PER_MINUTE = 120

_lock = threading.Lock()
_pairs: dict[tuple[str, str], deque[float]] = {}
_emails: dict[str, deque[float]] = {}
_trusted: dict[tuple[str, str], float] = {}
_new_key_times: deque[float] = deque()


def reset() -> None:
    with _lock:
        _pairs.clear()
        _emails.clear()
        _trusted.clear()
        _new_key_times.clear()


def _trim(attempts: deque[float], now: float) -> None:
    while attempts and now - attempts[0] >= WINDOW_SECONDS:
        attempts.popleft()


def _purge_expired(now: float) -> None:
    for table in (_pairs, _emails):
        for key in [k for k, v in table.items() if not v or now - v[-1] >= WINDOW_SECONDS]:
            del table[key]
    for key in [k for k, t in _trusted.items() if now - t >= TRUSTED_SECONDS]:
        del _trusted[key]


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many failed login attempts. Try again later.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _admit_new_key(now: float) -> bool:
    """Whether a key not yet tracked may be created while the maps are at capacity."""
    if len(_pairs) + len(_emails) < MAX_TRACKED_KEYS:
        return True
    _purge_expired(now)
    if len(_pairs) + len(_emails) < MAX_TRACKED_KEYS:
        return True
    while _new_key_times and now - _new_key_times[0] >= 60:
        _new_key_times.popleft()
    if len(_new_key_times) >= FULL_MAP_NEW_KEYS_PER_MINUTE:
        return False
    _new_key_times.append(now)
    return True


def reserve_login_attempt(email: str, client: str, *, now: float | None = None) -> float:
    """Count this attempt, or raise 429. Returns the reservation token for release.

    The check and the increment happen under one lock; a failure simply leaves the
    reservation in place, a success hands it back via release_login_attempt().
    """
    current = time.monotonic() if now is None else now
    pair = (email, client)
    with _lock:
        pair_attempts = _pairs.get(pair)
        email_attempts = _emails.get(email)
        if pair_attempts is None or email_attempts is None:
            if not _admit_new_key(current):
                raise _too_many(60)
        if pair_attempts is not None:
            _trim(pair_attempts, current)
        if email_attempts is not None:
            _trim(email_attempts, current)

        if pair_attempts is not None and len(pair_attempts) >= MAX_PAIR_ATTEMPTS:
            raise _too_many(int(WINDOW_SECONDS - (current - pair_attempts[0])) + 1)
        trusted_at = _trusted.get(pair)
        is_trusted = (
            trusted_at is not None
            and current - trusted_at < TRUSTED_SECONDS
            and not pair_attempts
        )
        if (
            email_attempts is not None
            and len(email_attempts) >= MAX_EMAIL_ATTEMPTS
            and not is_trusted
        ):
            raise _too_many(int(WINDOW_SECONDS - (current - email_attempts[0])) + 1)

        if pair_attempts is None:
            pair_attempts = _pairs.setdefault(pair, deque())
        if email_attempts is None:
            email_attempts = _emails.setdefault(email, deque())
        pair_attempts.append(current)
        email_attempts.append(current)
        return current


def release_login_attempt(email: str, client: str, token: float, *, now: float | None = None) -> None:
    """Successful login: give the reservation back and remember the pair as familiar."""
    current = time.monotonic() if now is None else now
    pair = (email, client)
    with _lock:
        for table, key in ((_pairs, pair), (_emails, email)):
            attempts = table.get(key)
            if attempts is None:
                continue
            try:
                attempts.remove(token)
            except ValueError:
                pass
            if not attempts:
                del table[key]
        if len(_trusted) < MAX_TRACKED_KEYS or pair in _trusted:
            _trusted[pair] = current
