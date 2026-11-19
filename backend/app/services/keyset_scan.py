"""Keyset-paginated reads for maintenance jobs that interleave the database with slow I/O.

Two production limits shape every long-running catalog job:

* `statement_timeout` (8 s on request sessions, 15 min on background sessions): one
  `SELECT games.* FROM games` over ~50k rows with their JSON columns does not finish in
  time, so scans select only the columns they use, `batch_size` rows per statement.
* `idle_in_transaction_session_timeout` (60 s, server-wide): a transaction left open
  while the job sleeps between Steam/ProtonDB requests gets the connection killed.
  With `release=True` each batch's read transaction ends (rollback of a read-only
  transaction) *before* the batch is handed to the caller, so no transaction is open
  while the caller does network I/O. Writes happen later in their own short
  transactions.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Row, Select
from sqlalchemy.orm import InstrumentedAttribute, Session

SCAN_BATCH_SIZE = 1000


def keyset_batches(
    db: Session,
    stmt: Select[Any],
    key: InstrumentedAttribute[int],
    *,
    batch_size: int = SCAN_BATCH_SIZE,
    after: int = 0,
    limit: int | None = None,
    release: bool = True,
) -> Iterator[list[Row[Any]]]:
    """Yield `stmt` rows in ascending `key` order, `batch_size` per statement.

    `stmt` must select `key` (by its attribute name) and carry no ORDER BY / LIMIT.
    `release=True` rolls back after every read: the session must have nothing
    pending, which holds for callers that commit each write burst themselves.
    """
    remaining = limit
    last = after
    while remaining is None or remaining > 0:
        size = batch_size if remaining is None else min(batch_size, remaining)
        rows = list(db.execute(stmt.where(key > last).order_by(key).limit(size)).all())
        if release:
            db.rollback()
        if not rows:
            return
        yield rows
        last = getattr(rows[-1], key.key)
        if remaining is not None:
            remaining -= len(rows)
        if len(rows) < size:
            return
