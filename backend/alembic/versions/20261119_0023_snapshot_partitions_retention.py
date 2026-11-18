"""Monthly-partitioned snapshot tables, history trimmed to what is read.

rating_snapshots and source_snapshots become RANGE partitions on fetched_at. Only the last 30
days plus the LATEST row per key are copied (rating: game_id+source; source snapshot:
source+endpoint+external_id, or +query when there is no external id); everything else is
history nothing reads. Rows older than the retention month land in the DEFAULT partition.
The duplicate PK indexes (ix_*_id) and the unused ix_source_snapshots_source are not recreated.
api_request_windows loses windows that ended > 2 days ago plus its redundant indexes, and
data_fill_runs loses the big result JSON of all but the newest 5 runs.

The whole upgrade runs in one transaction. A database that is already partitioned (a fresh
install whose baseline create_all() built the current models) is left alone.

Downgrade restores the flat tables and indexes. The deleted history does NOT come back.

Revision ID: 20261119_0023
Revises: 20261119_0022
"""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op


revision = "20261119_0023"
down_revision = "20261119_0022"
branch_labels = None
depends_on = None

_RATING_COLUMNS = (
    "id, game_id, source, score, score_normalized, rating_count, review_count, critic_count, "
    "user_count, is_critic, is_user, is_applicable, confidence, raw_payload, fetched_at, created_at"
)
_SOURCE_COLUMNS = (
    "id, source, endpoint, query, external_id, status_code, raw_payload, fetched_at, created_at"
)
_KEYS = {
    "rating_snapshots": "game_id, source",
    "source_snapshots": (
        "source, endpoint, COALESCE(external_id, ''), "
        "CASE WHEN external_id IS NULL THEN COALESCE(query, '') ELSE '' END"
    ),
}
_COLUMNS = {"rating_snapshots": _RATING_COLUMNS, "source_snapshots": _SOURCE_COLUMNS}

_DDL = {
    "rating_snapshots": """
        CREATE TABLE rating_snapshots (
            id SERIAL NOT NULL,
            game_id INTEGER NOT NULL,
            source VARCHAR(60) NOT NULL,
            score DOUBLE PRECISION,
            score_normalized DOUBLE PRECISION,
            rating_count INTEGER NOT NULL,
            review_count INTEGER NOT NULL,
            critic_count INTEGER,
            user_count INTEGER,
            is_critic BOOLEAN NOT NULL,
            is_user BOOLEAN NOT NULL,
            is_applicable BOOLEAN NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            raw_payload JSON,
            fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id, fetched_at),
            FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE
        ) PARTITION BY RANGE (fetched_at)
    """,
    "source_snapshots": """
        CREATE TABLE source_snapshots (
            id SERIAL NOT NULL,
            source VARCHAR(60) NOT NULL,
            endpoint VARCHAR(300) NOT NULL,
            query VARCHAR(300),
            external_id VARCHAR(200),
            status_code INTEGER,
            raw_payload JSON,
            fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id, fetched_at)
        ) PARTITION BY RANGE (fetched_at)
    """,
}
_INDEXES = {
    "rating_snapshots": (
        "CREATE INDEX ix_rating_snapshots_game_source ON rating_snapshots (game_id, source, fetched_at)",
    ),
    "source_snapshots": (
        "CREATE INDEX ix_source_snapshots_lookup ON source_snapshots "
        "(source, endpoint, external_id, fetched_at)",
    ),
}


def _month_start(moment: datetime) -> datetime:
    return datetime(moment.year, moment.month, 1, tzinfo=UTC)


def _next_month(moment: datetime) -> datetime:
    return datetime(moment.year + (moment.month == 12), moment.month % 12 + 1, 1, tzinfo=UTC)


def _is_partitioned(bind, table: str) -> bool:
    kind = bind.execute(
        sa.text("SELECT relkind FROM pg_class WHERE oid = to_regclass(:t)"), {"t": table}
    ).scalar()
    return kind == "p"


def _retire_old_table(bind, table: str) -> None:
    """Rename the flat table out of the way (and its PK/sequence), drop FK and other indexes."""
    bind.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_game_id_fkey"))
    for index in (f"ix_{table}_id", f"ix_{table}_game_id", f"ix_{table}_source", f"ix_{table}_lookup"):
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {index}"))
    bind.execute(sa.text(f"ALTER TABLE {table} RENAME TO {table}_old"))
    bind.execute(sa.text(f"ALTER TABLE IF EXISTS {table}_old RENAME CONSTRAINT {table}_pkey TO {table}_old_pkey"))
    bind.execute(sa.text(f"ALTER SEQUENCE IF EXISTS {table}_id_seq RENAME TO {table}_old_id_seq"))


def _partition_one(bind, table: str, now: datetime) -> None:
    if not _is_partitioned(bind, table) and bind.execute(
        sa.text("SELECT to_regclass(:t)"), {"t": table}
    ).scalar() is None:
        return
    if _is_partitioned(bind, table):
        return
    cutoff = now - timedelta(days=30)
    bind.execute(sa.text(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"))
    _retire_old_table(bind, table)
    bind.execute(sa.text(_DDL[table]))
    bind.execute(sa.text(f"CREATE TABLE {table}_default PARTITION OF {table} DEFAULT"))
    start, last = _month_start(cutoff), _next_month(_next_month(_next_month(_month_start(now))))
    while start <= last:
        end = _next_month(start)
        bind.execute(
            sa.text(
                f"CREATE TABLE {table}_p{start:%Y%m} PARTITION OF {table} "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )
        start = end
    # Narrow ids first: sorting only key columns keeps the sort small in a 224 MB container.
    bind.execute(
        sa.text(
            f"CREATE TEMP TABLE {table}_keep ON COMMIT DROP AS "
            f"SELECT DISTINCT ON ({_KEYS[table]}) id FROM {table}_old "
            f"ORDER BY {_KEYS[table]}, fetched_at DESC, id DESC"
        )
    )
    bind.execute(sa.text(f"CREATE UNIQUE INDEX ON {table}_keep (id)"))
    bind.execute(
        sa.text(
            f"INSERT INTO {table} ({_COLUMNS[table]}) SELECT {_COLUMNS[table]} FROM {table}_old o "
            f"WHERE o.fetched_at >= :cutoff OR EXISTS (SELECT 1 FROM {table}_keep k WHERE k.id = o.id)"
        ),
        {"cutoff": cutoff},
    )
    bind.execute(sa.text(f"DROP TABLE {table}_old"))
    bind.execute(
        sa.text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)"
        )
    )
    for statement in _INDEXES[table]:
        bind.execute(sa.text(statement))
    bind.execute(sa.text(f"ANALYZE {table}"))


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    for table in ("rating_snapshots", "source_snapshots"):
        _partition_one(bind, table, now)

    # Quota windows: only the window containing "now" is ever read.
    op.execute("DROP INDEX IF EXISTS ix_api_request_windows_id")
    op.execute("DROP INDEX IF EXISTS ix_api_request_windows_source")
    op.execute(
        "DELETE FROM api_request_windows WHERE window_start < now() - interval '2 days' "
        "AND window_start + make_interval(secs => window_seconds) < now() - interval '2 days'"
    )
    op.execute(
        "UPDATE data_fill_runs SET result = '{}'::json, error = left(error, 500) "
        "WHERE id NOT IN (SELECT id FROM data_fill_runs ORDER BY started_at DESC, id DESC LIMIT 5) "
        "AND (result::text <> '{}' OR length(error) > 500)"
    )


def _flatten(bind, table: str) -> None:
    if not _is_partitioned(bind, table):
        return
    ddl = _DDL[table].split(") PARTITION BY")[0].replace(
        "PRIMARY KEY (id, fetched_at)", "PRIMARY KEY (id)"
    ).replace(f"CREATE TABLE {table} (", f"CREATE TABLE {table}_flat (") + ")"
    ddl = ddl.replace("FOREIGN KEY (game_id)", f"CONSTRAINT {table}_flat_game_id_fkey FOREIGN KEY (game_id)")
    bind.execute(sa.text(ddl))
    bind.execute(
        sa.text(
            f"INSERT INTO {table}_flat ({_COLUMNS[table]}) SELECT {_COLUMNS[table]} FROM {table}"
        )
    )
    bind.execute(sa.text(f"DROP TABLE {table}"))
    bind.execute(sa.text(f"ALTER TABLE {table}_flat RENAME TO {table}"))
    bind.execute(sa.text(f"ALTER TABLE {table} RENAME CONSTRAINT {table}_flat_pkey TO {table}_pkey"))
    bind.execute(sa.text(f"ALTER SEQUENCE {table}_flat_id_seq RENAME TO {table}_id_seq"))
    bind.execute(
        sa.text(
            f"SELECT setval('{table}_id_seq', COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)"
        )
    )
    bind.execute(sa.text(f"CREATE INDEX ix_{table}_id ON {table} (id)"))
    if table == "rating_snapshots":
        bind.execute(sa.text(f"ALTER TABLE {table} RENAME CONSTRAINT {table}_flat_game_id_fkey TO {table}_game_id_fkey"))
        bind.execute(sa.text("CREATE INDEX ix_rating_snapshots_game_id ON rating_snapshots (game_id)"))
    else:
        bind.execute(sa.text("CREATE INDEX ix_source_snapshots_source ON source_snapshots (source)"))
        bind.execute(
            sa.text(
                "CREATE INDEX ix_source_snapshots_lookup ON source_snapshots "
                "(source, endpoint, external_id, fetched_at)"
            )
        )


def downgrade() -> None:
    """Restore the flat tables and indexes. Deleted history is gone for good."""
    bind = op.get_bind()
    for table in ("rating_snapshots", "source_snapshots"):
        _flatten(bind, table)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_request_windows_id ON api_request_windows (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_request_windows_source ON api_request_windows (source)")
