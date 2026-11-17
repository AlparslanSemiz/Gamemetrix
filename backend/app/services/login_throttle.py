"""Failed-login limits, kept in Postgres.

State survives restarts and is shared by every process; there is no map to fill up or evict
from. Rows are keyed `email:<normalized e-mail>` and `pair:<normalized e-mail>|<client /64>`,
and rows older than the window are deleted daily (purge_expired).

* Pair (e-mail, client): at most MAX_PAIR_ATTEMPTS per WINDOW_SECONDS, then 429. The client is
  part of the key, so someone guessing a victim's address locks out only themselves. A trusted
  device only gets the looser TRUSTED_PAIR_ATTEMPTS limit, never a bypass.
* E-mail: past MAX_EMAIL_ATTEMPTS per window every accepted attempt pushes `next_allowed_at`
  out exponentially (1, 2, 4 ... at most 60 s). Requests arriving before it answer 429 with
  Retry-After, so concurrent requests cannot jump the wait, yet the owner is only ever asked
  to wait a minute. Trusted devices skip this layer.

Each attempt is reserved with a single INSERT ... ON CONFLICT DO UPDATE ... RETURNING (the
check and the increment are one atomic statement) before the password is verified, and handed
back on success.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_PAIR_ATTEMPTS = 10
TRUSTED_PAIR_ATTEMPTS = 30
MAX_EMAIL_ATTEMPTS = 20
WINDOW_SECONDS = 15 * 60
MAX_DELAY_SECONDS = 60

_RESERVE = text(
    """
    INSERT INTO login_throttle AS t (key, kind, failures, window_start, next_allowed_at)
    VALUES (:key, :kind, 1, :now, NULL)
    ON CONFLICT (key) DO UPDATE SET
      failures = CASE WHEN t.window_start <= :now - make_interval(secs => :window)
                      THEN 1 ELSE t.failures + 1 END,
      window_start = CASE WHEN t.window_start <= :now - make_interval(secs => :window)
                          THEN :now ELSE t.window_start END,
      next_allowed_at = CASE
        WHEN :hard OR t.window_start <= :now - make_interval(secs => :window) THEN NULL
        WHEN t.failures + 1 > :limit THEN :now + make_interval(
          secs => LEAST(CAST(:max_delay AS double precision),
                        power(2.0, LEAST(t.failures + 1 - :limit - 1, 6))))
        ELSE NULL END
    WHERE t.window_start <= :now - make_interval(secs => :window)
       OR ((NOT :hard OR t.failures < :limit)
           AND (t.next_allowed_at IS NULL OR t.next_allowed_at <= :now))
    RETURNING failures
    """
)
_STATE = text("SELECT window_start, next_allowed_at FROM login_throttle WHERE key = :key")
_RELEASE = text(
    "UPDATE login_throttle SET failures = GREATEST(failures - 1, 0), next_allowed_at = NULL "
    "WHERE key = ANY(:keys)"
)
_PURGE = text("DELETE FROM login_throttle WHERE window_start < :cutoff")


@dataclass(frozen=True)
class Reservation:
    keys: tuple[str, ...]


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def _reserve_one(db: Session, key: str, kind: str, limit: int, hard: bool, now: datetime) -> bool:
    row = db.execute(
        _RESERVE,
        {
            "key": key, "kind": kind, "now": now, "window": WINDOW_SECONDS, "hard": hard,
            "limit": limit, "max_delay": MAX_DELAY_SECONDS,
        },
    ).first()
    return row is not None


def _retry_after(db: Session, key: str, now: datetime) -> int:
    state = db.execute(_STATE, {"key": key}).first()
    if state is None:
        return 1
    window_start, next_allowed = state
    waits = [(window_start + timedelta(seconds=WINDOW_SECONDS) - now).total_seconds()]
    if next_allowed is not None and next_allowed > now:
        waits = [(next_allowed - now).total_seconds()]
    return max(1, int(waits[0]) + 1)


def reserve_login_attempt(
    db: Session,
    email: str,
    client: str,
    *,
    trusted_device: bool = False,
    now: datetime | None = None,
) -> Reservation:
    """Count this attempt or raise 429 with Retry-After. Commits on success."""
    current = _now(now)
    pair_key = f"pair:{email}|{client}"
    email_key = f"email:{email}"
    pair_limit = TRUSTED_PAIR_ATTEMPTS if trusted_device else MAX_PAIR_ATTEMPTS
    keys = [pair_key]
    blocked_key: str | None = None
    if not _reserve_one(db, pair_key, "pair", pair_limit, True, current):
        blocked_key = pair_key
    elif not trusted_device:
        keys.append(email_key)
        if not _reserve_one(db, email_key, "email", MAX_EMAIL_ATTEMPTS, False, current):
            blocked_key = email_key
    if blocked_key is not None:
        db.rollback()  # discards the pair increment made in this same transaction
        retry = _retry_after(db, blocked_key, current)
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again shortly.",
            headers={"Retry-After": str(retry)},
        )
    db.commit()
    return Reservation(tuple(keys))


def release_login_attempt(db: Session, reservation: Reservation) -> None:
    """Successful login: hand the reserved attempt back."""
    db.execute(_RELEASE, {"keys": list(reservation.keys)})
    db.commit()


def purge_expired(db: Session, *, now: datetime | None = None) -> int:
    from ..models import TrustedDevice

    current = _now(now)
    removed = db.execute(_PURGE, {"cutoff": current - timedelta(seconds=WINDOW_SECONDS)}).rowcount
    removed += db.query(TrustedDevice).filter(TrustedDevice.expires_at < current).delete()
    db.commit()
    return int(removed or 0)
