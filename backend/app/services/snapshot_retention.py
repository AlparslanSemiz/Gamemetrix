"""Retention for the append-only history tables (snapshots, quota windows, data-fill runs).

rating_snapshots and source_snapshots are monthly RANGE partitions on fetched_at. Only two kinds
of history is ever read: the LAST 30 DAYS, and the LATEST row per key (rating: game+source;
source snapshot: source+endpoint+external_id, or +query when there is no external id). The
latest row is what persistence compares against and what the 30/90-day "do not retry yet"
caches look at, so it must survive however old it is.

Sweep, run from the retention loop:
  1. create monthly partitions from the retention horizon up to PARTITIONS_AHEAD months ahead;
  2. every partition that ends before the horizon is DETACHed; its still-latest rows are
     re-inserted into the parent (they route to the DEFAULT partition, which holds exactly that
     long-lived "latest only" set) and the detached table is DROPped. No bulk DELETE, no bloat;
  3. rows in the DEFAULT partition superseded by a newer row are deleted (a small table);
  4. api_request_windows rows whose window ended more than 2 days ago are deleted in batches;
  5. data_fill_runs keeps the newest runs in full and clears the big `result` JSON of older ones.

Partitions are 30-60 days deep in practice (the partition containing the horizon stays whole).
DETACH is the plain, short ACCESS EXCLUSIVE form: DETACH ... CONCURRENTLY is refused by
PostgreSQL while a DEFAULT partition exists. A lock timeout makes a busy sweep retry next cycle.
"""

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("gamemetrix.snapshot_retention")

SNAPSHOT_RETENTION_DAYS = 30
PARTITIONS_AHEAD = 3
API_WINDOW_GRACE = timedelta(days=2)
API_WINDOW_BATCH = 20_000
DATA_FILL_FULL_RUNS = 5
_LOCK_TIMEOUT = "5s"

# table -> ONE text expression identifying "the same record" for the latest-row rule. It must be
# a single expression: with a multi-column key the planner merge-joins on the first two columns
# only (every source snapshot shares source/endpoint) and filters the rest, which is quadratic.
_KEYS: dict[str, str] = {
    "rating_snapshots": "({a}.game_id::text || chr(31) || {a}.source)",
    "source_snapshots": (
        "({a}.source || chr(31) || {a}.endpoint || chr(31) || COALESCE({a}.external_id, '') "
        "|| chr(31) || CASE WHEN {a}.external_id IS NULL THEN COALESCE({a}.query, '') ELSE '' END)"
    ),
}
_PARTITION_NAME = re.compile(r"^(?P<table>[a-z_]+)_p(?P<year>\d{4})(?P<month>\d{2})$")


def month_start(moment: datetime) -> datetime:
    return datetime(moment.year, moment.month, 1, tzinfo=UTC)


def next_month(moment: datetime) -> datetime:
    return datetime(moment.year + (moment.month == 12), moment.month % 12 + 1, 1, tzinfo=UTC)


_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _ident(name: str) -> str:
    """Only our own table/partition names reach the dynamic SQL below; refuse anything else."""
    base = name.removesuffix("_default")
    base = re.sub(r"_p\d{6}$", "", base)
    if base not in _KEYS or not _IDENT.match(name):
        raise ValueError(f"unexpected table identifier: {name!r}")
    return name


def partition_name(table: str, start: datetime) -> str:
    return _ident(f"{table}_p{start:%Y%m}")


def ensure_partitions(db: Session, table: str, now: datetime) -> list[str]:
    """Create the monthly partitions from the retention horizon to PARTITIONS_AHEAD months ahead."""
    created: list[str] = []
    start = month_start(now - timedelta(days=SNAPSHOT_RETENTION_DAYS))
    last = month_start(now)
    for _ in range(PARTITIONS_AHEAD):
        last = next_month(last)
    while start <= last:
        end = next_month(start)
        name = partition_name(table, start)
        exists = db.scalar(text("SELECT to_regclass(:name)"), {"name": name})
        if exists is None:
            db.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
            # Rows already routed to the DEFAULT partition inside this range (a partition that
            # was missing when they arrived) would make a plain CREATE ... PARTITION OF fail,
            # so build the table first, move them in, then ATTACH.
            bounds = f"FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"  # nosec B608 - identifiers pass _ident(), values are bound
            db.execute(text(f"CREATE TABLE {name} (LIKE {table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"))  # nosec B608 - identifiers pass _ident(), values are bound
            db.execute(
                text(
                    f"WITH moved AS (DELETE FROM {table}_default "  # nosec B608 - identifiers pass _ident(), values are bound
                    f"WHERE fetched_at >= :start AND fetched_at < :end RETURNING *) "
                    f"INSERT INTO {name} SELECT * FROM moved"  # nosec B608 - identifiers pass _ident(), values are bound
                ),
                {"start": start, "end": end},
            )
            db.execute(text(f"ALTER TABLE {table} ATTACH PARTITION {name} FOR VALUES {bounds}"))  # nosec B608 - identifiers pass _ident(), values are bound
            created.append(name)
        start = end
    return created


def _expired_partitions(db: Session, table: str, horizon: datetime) -> list[tuple[str, datetime]]:
    rows = db.execute(
        text(
            "SELECT c.relname FROM pg_inherits i "
            "JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = to_regclass(:table) ORDER BY c.relname"
        ),
        {"table": table},
    ).scalars()
    expired = []
    for relname in rows:
        relname = _ident(relname)
        match = _PARTITION_NAME.match(relname)
        if not match or match["table"] != table:
            continue
        start = datetime(int(match["year"]), int(match["month"]), 1, tzinfo=UTC)
        if next_month(start) <= horizon:
            expired.append((relname, next_month(start)))
    return expired


def _latest_into_parent(db: Session, table: str, partition: str, upper: datetime) -> None:
    """Re-insert the still-latest rows of a detached partition (they route to DEFAULT).

    Two steps keep memory flat: the sort and the anti-join run over narrow (id, key) tuples,
    only the surviving ids are joined back to the wide rows that carry raw_payload.
    """
    key_p = _KEYS[table].format(a="p")
    key_n = _KEYS[table].format(a="n")
    db.execute(text("DROP TABLE IF EXISTS _retention_keep"))
    db.execute(
        text(
            f"CREATE TEMP TABLE _retention_keep ON COMMIT DROP AS "  # nosec B608 - identifiers pass _ident(), values are bound
            f"SELECT c.id FROM (SELECT DISTINCT ON ({key_p}) p.id, {key_p} AS k "  # nosec B608 - identifiers pass _ident(), values are bound
            f"FROM {partition} p ORDER BY {key_p}, p.fetched_at DESC, p.id DESC) c "  # nosec B608 - identifiers pass _ident(), values are bound
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} n WHERE n.fetched_at >= :upper "  # nosec B608 - identifiers pass _ident(), values are bound
            f"AND {key_n} = c.k)"
        ),
        {"upper": upper},
    )
    db.execute(text("CREATE UNIQUE INDEX ON _retention_keep (id)"))
    db.execute(
        text(
            f"INSERT INTO {table} SELECT p.* FROM {partition} p "  # nosec B608 - identifiers pass _ident(), values are bound
            f"WHERE EXISTS (SELECT 1 FROM _retention_keep k WHERE k.id = p.id)"  # nosec B608 - identifiers pass _ident(), values are bound
        )
    )


def drop_expired_partitions(db_factory, table: str, now: datetime) -> list[str]:
    """DETACH + DROP partitions that end before the horizon, keeping their latest rows."""
    horizon = now - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    with db_factory() as db:
        expired = _expired_partitions(db, table, horizon)
    dropped = []
    for relname, upper in expired:
        try:
            with db_factory() as db:
                db.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
                db.execute(text(f"ALTER TABLE {table} DETACH PARTITION {relname}"))  # nosec B608 - identifiers pass _ident(), values are bound
                _latest_into_parent(db, table, relname, upper)
                db.execute(text(f"DROP TABLE {relname}"))  # nosec B608 - identifiers pass _ident(), values are bound
                db.commit()
            dropped.append(relname)
        except Exception:
            log.warning("Could not retire partition %s now; retrying next sweep", relname, exc_info=True)
    return dropped


def prune_default_partition(db: Session, table: str) -> int:
    """Delete rows in the DEFAULT partition that a newer row of the same key supersedes."""
    key_n = _KEYS[table].format(a="n")
    key_d = _KEYS[table].format(a="d")
    result = db.execute(
        text(
            f"DELETE FROM {table}_default d WHERE EXISTS (SELECT 1 FROM {table} n "  # nosec B608 - identifiers pass _ident(), values are bound
            f"WHERE {key_n} = {key_d} AND (n.fetched_at > d.fetched_at "
            f"OR (n.fetched_at = d.fetched_at AND n.id > d.id)))"
        )
    )
    return int(result.rowcount or 0)


def purge_api_request_windows(db: Session, now: datetime) -> int:
    """Delete quota windows that ended more than API_WINDOW_GRACE ago, in batches.

    A window is (window_start, window_start + window_seconds); the rate limiter only ever reads
    the window containing "now", so anything that ended days ago is dead weight (OpenCritic's
    1-second windows alone wrote ~400k rows).
    """
    cutoff = now - API_WINDOW_GRACE
    total = 0
    while True:
        result = db.execute(
            text(
                "DELETE FROM api_request_windows WHERE id IN ("
                "SELECT id FROM api_request_windows WHERE window_start < :cutoff "
                "AND window_start + make_interval(secs => window_seconds) < :cutoff LIMIT :batch)"
            ),
            {"cutoff": cutoff, "batch": API_WINDOW_BATCH},
        )
        db.commit()
        removed = int(result.rowcount or 0)
        total += removed
        if removed < API_WINDOW_BATCH:
            return total


def trim_data_fill_runs(db: Session) -> int:
    """Clear the (multi-MB) result JSON of every run but the newest DATA_FILL_FULL_RUNS."""
    result = db.execute(
        text(
            "UPDATE data_fill_runs SET result = '{}'::json, error = left(error, 500) "
            "WHERE id NOT IN (SELECT id FROM data_fill_runs ORDER BY started_at DESC, id DESC "
            "LIMIT :keep) AND (result::text <> '{}' OR length(error) > 500)"
        ),
        {"keep": DATA_FILL_FULL_RUNS},
    )
    db.commit()
    return int(result.rowcount or 0)


def run_snapshot_retention(db_factory, now: datetime | None = None) -> dict[str, object]:
    """One full sweep. `db_factory` yields sessions with a long statement timeout."""
    now = now or datetime.now(UTC)
    summary: dict[str, object] = {}
    for table in _KEYS:
        try:
            with db_factory() as db:
                summary[f"{table}_created"] = ensure_partitions(db, table, now)
                db.commit()
            summary[f"{table}_dropped"] = drop_expired_partitions(db_factory, table, now)
            with db_factory() as db:
                summary[f"{table}_default_pruned"] = prune_default_partition(db, table)
                db.commit()
        except Exception:
            log.exception("Snapshot retention failed for %s", table)
    try:
        with db_factory() as db:
            summary["api_request_windows_purged"] = purge_api_request_windows(db, now)
        with db_factory() as db:
            summary["data_fill_runs_trimmed"] = trim_data_fill_runs(db)
    except Exception:
        log.exception("Operational table retention failed")
    return summary
