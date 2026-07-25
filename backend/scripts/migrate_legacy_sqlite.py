"""Merge the legacy SQLite catalog into the configured PostgreSQL database.

The source database is opened read-only. Existing PostgreSQL games win on slug,
while legacy-only games and their related records are copied with remapped game
IDs. Large append-only snapshot tables are copied only when their PostgreSQL
counterpart is empty, which keeps reruns from duplicating history.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import Boolean, Date, DateTime, JSON, MetaData, Table, create_engine, func, insert, select
from sqlalchemy.engine import Connection, Engine


LEGACY_TABLES = (
    "games",
    "external_ids",
    "price_snapshots",
    "rating_snapshots",
    "source_snapshots",
    "visit_events",
)
GAME_RELATED_TABLES = frozenset(
    {"external_ids", "price_snapshots", "rating_snapshots"}
)
APPEND_ONLY_TABLES = frozenset(
    {"price_snapshots", "rating_snapshots", "source_snapshots", "visit_events"}
)
DEFAULT_BATCH_SIZE = 500


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "gamemetrix.dev.db",
        help="Legacy SQLite database (default: backend/gamemetrix.dev.db).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag the command only reports a plan.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Insert batch size (default: {DEFAULT_BATCH_SIZE}).",
    )
    return parser.parse_args()


def _database_url() -> str:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required.")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must point to PostgreSQL with postgresql+psycopg://.")
    return url


def _open_source(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Legacy SQLite database not found: {resolved}")
    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _source_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _source_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    quoted = table.replace('"', '""')
    return [
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{quoted}")')
    ]


def _source_count(connection: sqlite3.Connection, table: str) -> int:
    quoted = table.replace('"', '""')
    return int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])


def _chunks(rows: Iterable[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # Preserve malformed legacy payloads as valid JSON strings instead of
        # discarding them or aborting the entire migration.
        return value


def _date_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def coerce_value(column, value: Any) -> Any:
    """Convert a SQLite value into the reflected PostgreSQL column type."""
    if value is None:
        return None
    if isinstance(column.type, JSON):
        return _json_value(value)
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime):
        return _datetime_value(value)
    if isinstance(column.type, Date):
        return _date_value(value)
    return value


def _iter_source_rows(
    source: sqlite3.Connection,
    target: Table,
    *,
    game_id_map: Mapping[int, int] | None = None,
) -> Iterator[dict[str, Any]]:
    source_names = set(_source_columns(source, target.name))
    columns = [
        column
        for column in target.columns
        if column.name != "id" and column.name in source_names
    ]
    quoted_columns = ", ".join(f'"{column.name}"' for column in columns)
    for raw in source.execute(f'SELECT {quoted_columns} FROM "{target.name}"'):
        values = {
            column.name: coerce_value(column, raw[column.name])
            for column in columns
        }
        if target.name in GAME_RELATED_TABLES:
            source_game_id = int(values["game_id"])
            if game_id_map is None or source_game_id not in game_id_map:
                continue
            values["game_id"] = game_id_map[source_game_id]
        yield values


def _target_count(connection: Connection, table: Table) -> int:
    return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def _load_target_slugs(connection: Connection, games: Table) -> dict[str, int]:
    return {
        str(row.slug): int(row.id)
        for row in connection.execute(select(games.c.id, games.c.slug))
    }


def _legacy_game_map(
    source: sqlite3.Connection,
    target_slugs: Mapping[str, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for row in source.execute("SELECT id, slug FROM games"):
        target_id = target_slugs.get(str(row["slug"]))
        if target_id is not None:
            mapping[int(row["id"])] = target_id
    return mapping


def _insert_legacy_only_games(
    connection: Connection,
    source: sqlite3.Connection,
    games: Table,
    *,
    existing_slugs: set[str],
    batch_size: int,
) -> int:
    rows = (
        row
        for row in _iter_source_rows(source, games)
        if str(row["slug"]) not in existing_slugs
    )
    inserted = 0
    for batch in _chunks(rows, batch_size):
        connection.execute(insert(games), batch)
        inserted += len(batch)
        print(f"games: inserted={inserted}", flush=True)
    return inserted


def _insert_table(
    connection: Connection,
    source: sqlite3.Connection,
    target: Table,
    *,
    game_id_map: Mapping[int, int],
    batch_size: int,
) -> int:
    inserted = 0
    for batch in _chunks(
        _iter_source_rows(source, target, game_id_map=game_id_map),
        batch_size,
    ):
        connection.execute(insert(target), batch)
        inserted += len(batch)
        if inserted % (batch_size * 20) == 0:
            print(f"{target.name}: inserted={inserted}", flush=True)
    print(f"{target.name}: inserted={inserted}", flush=True)
    return inserted


def _plan(
    source: sqlite3.Connection,
    engine: Engine,
    tables: Mapping[str, Table],
) -> dict[str, int]:
    with engine.connect() as connection:
        target_slugs = _load_target_slugs(connection, tables["games"])
        source_game_rows = source.execute("SELECT id, slug FROM games").fetchall()
        overlap = sum(1 for row in source_game_rows if str(row["slug"]) in target_slugs)
        plan = {
            "source_games": len(source_game_rows),
            "target_games": len(target_slugs),
            "overlap_games": overlap,
            "new_games": len(source_game_rows) - overlap,
        }
        for name in LEGACY_TABLES[1:]:
            plan[f"source_{name}"] = _source_count(source, name)
            plan[f"target_{name}"] = _target_count(connection, tables[name])
        return plan


def migrate(
    source: sqlite3.Connection,
    engine: Engine,
    tables: Mapping[str, Table],
    *,
    batch_size: int,
) -> dict[str, int]:
    result: dict[str, int] = {}

    with engine.begin() as connection:
        existing_slugs = set(_load_target_slugs(connection, tables["games"]))
        result["games"] = _insert_legacy_only_games(
            connection,
            source,
            tables["games"],
            existing_slugs=existing_slugs,
            batch_size=batch_size,
        )

    with engine.connect() as connection:
        game_id_map = _legacy_game_map(
            source,
            _load_target_slugs(connection, tables["games"]),
        )
    if len(game_id_map) != _source_count(source, "games"):
        raise RuntimeError("Not every legacy game could be mapped to PostgreSQL.")

    for name in LEGACY_TABLES[1:]:
        table = tables[name]
        with engine.connect() as connection:
            target_count = _target_count(connection, table)
        if name in APPEND_ONLY_TABLES and target_count:
            print(
                f"{name}: skipped because PostgreSQL already contains {target_count} rows",
                flush=True,
            )
            result[name] = 0
            continue
        if name == "external_ids" and target_count:
            print(
                "external_ids: skipped because PostgreSQL already contains rows",
                flush=True,
            )
            result[name] = 0
            continue
        with engine.begin() as connection:
            result[name] = _insert_table(
                connection,
                source,
                table,
                game_id_map=game_id_map,
                batch_size=batch_size,
            )
    return result


def main() -> None:
    args = _arguments()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive.")

    engine = create_engine(_database_url(), pool_pre_ping=True)
    metadata = MetaData()
    tables = {
        name: Table(name, metadata, autoload_with=engine)
        for name in LEGACY_TABLES
    }
    with _open_source(args.source) as source:
        missing = set(LEGACY_TABLES) - _source_tables(source)
        if missing:
            raise RuntimeError(
                "Legacy database is missing tables: " + ", ".join(sorted(missing))
            )
        plan = _plan(source, engine, tables)
        for key, value in plan.items():
            print(f"{key}={value}")
        if not args.apply:
            print("dry_run=true; rerun with --apply to migrate")
            return
        result = migrate(
            source,
            engine,
            tables,
            batch_size=args.batch_size,
        )
        print("migration_complete=true")
        for key, value in result.items():
            print(f"inserted_{key}={value}")


if __name__ == "__main__":
    main()
