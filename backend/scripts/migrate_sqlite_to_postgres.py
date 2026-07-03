"""
Copy GameMetrix data from a legacy SQLite database into PostgreSQL.

The script is idempotent:
- games are matched by slug
- related rows are matched by stable natural keys
- old SQLite game_id values are remapped to PostgreSQL game IDs

It never truncates or drops PostgreSQL tables.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.sqltypes import Boolean, Date, DateTime, JSON

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Base, ExternalId, Game, PriceSnapshot, RatingSnapshot, SourceSnapshot


T = TypeVar("T")

DEFAULT_SQLITE_PATH = Path("/tmp/gamemetrix.dev.db")
DEFAULT_POSTGRES_URL = "postgresql+psycopg://admin:password123@db:5432/gamemetrix"

MIGRATED_TABLES = (
    "games",
    "external_ids",
    "price_snapshots",
    "rating_snapshots",
    "source_snapshots",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate GameMetrix SQLite data to PostgreSQL.")
    parser.add_argument(
        "--sqlite",
        default=os.getenv("SQLITE_PATH", str(DEFAULT_SQLITE_PATH)),
        help="Path to the legacy SQLite DB inside this runtime.",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("POSTGRES_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_POSTGRES_URL,
        help="PostgreSQL SQLAlchemy URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate connectivity and print counts without writing.",
    )
    return parser.parse_args()


def sqlite_connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"SQLite database is empty: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    if not sqlite_table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def sqlite_rows(conn: sqlite3.Connection, table: str) -> Iterable[dict[str, Any]]:
    if not sqlite_table_exists(conn, table):
        return []
    return (dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"))


def model_columns(model: type[Any]) -> dict[str, Any]:
    return {column.name: column for column in inspect(model).columns}


def parse_date_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text[:19])
        except ValueError:
            return None


def parse_json_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def coerce_value(column: Any, value: Any) -> Any:
    column_type = column.type
    if isinstance(column_type, JSON):
        default = [] if not column.nullable else None
        return parse_json_value(value, default)
    if isinstance(column_type, DateTime):
        return parse_datetime_value(value)
    if isinstance(column_type, Date):
        return parse_date_value(value)
    if isinstance(column_type, Boolean):
        return bool(value) if value is not None else False
    return value


def build_payload(model: type[Any], row: dict[str, Any], *, skip: set[str] | None = None) -> dict[str, Any]:
    skip = skip or set()
    payload: dict[str, Any] = {}
    for name, column in model_columns(model).items():
        if name == "id" or name in skip or name not in row:
            continue
        payload[name] = coerce_value(column, row[name])
    return payload


def update_model(instance: Any, payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        setattr(instance, key, value)


def pg_count(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count(model.id))) or 0)


def first_or_none(session: Session, model: type[T], *criteria: Any) -> T | None:
    return session.scalar(select(model).where(*criteria).limit(1))


def migrate_games(sqlite_conn: sqlite3.Connection, pg: Session, dry_run: bool) -> tuple[dict[int, int], dict[str, int]]:
    id_map: dict[int, int] = {}
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    existing_by_slug = {
        game.slug: game
        for game in pg.scalars(select(Game)).all()
    }

    for row in sqlite_rows(sqlite_conn, "games"):
        old_id = int(row["id"])
        slug = (row.get("slug") or "").strip()
        if not slug:
            stats["skipped"] += 1
            continue

        existing = existing_by_slug.get(slug)
        payload = build_payload(Game, row)

        if dry_run:
            if existing:
                id_map[old_id] = int(existing.id)
                stats["updated"] += 1
            else:
                id_map[old_id] = -old_id
                stats["inserted"] += 1
            continue

        if existing:
            update_model(existing, payload)
            pg.add(existing)
            pg.flush()
            id_map[old_id] = int(existing.id)
            stats["updated"] += 1
        else:
            game = Game(**payload)
            pg.add(game)
            pg.flush()
            id_map[old_id] = int(game.id)
            existing_by_slug[slug] = game
            stats["inserted"] += 1

    return id_map, stats


def external_id_key(row: ExternalId | dict[str, Any]) -> tuple[Any, ...]:
    return (value(row, "game_id"), value(row, "source"), value(row, "external_id"))


def price_snapshot_key(row: PriceSnapshot | dict[str, Any]) -> tuple[Any, ...]:
    external_price_id = value(row, "external_price_id")
    if external_price_id:
        return (
            value(row, "game_id"),
            value(row, "source"),
            value(row, "store"),
            value(row, "region"),
            external_price_id,
        )
    return (
        value(row, "game_id"),
        value(row, "source"),
        value(row, "store"),
        value(row, "region"),
        value(row, "platform"),
        value(row, "currency"),
        value(row, "fetched_at"),
    )


def rating_snapshot_key(row: RatingSnapshot | dict[str, Any]) -> tuple[Any, ...]:
    return (value(row, "game_id"), value(row, "source"), value(row, "fetched_at"))


def source_snapshot_key(row: SourceSnapshot | dict[str, Any]) -> tuple[Any, ...]:
    return (
        value(row, "source"),
        value(row, "endpoint"),
        value(row, "query"),
        value(row, "external_id"),
        value(row, "fetched_at"),
    )


def value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key)


def existing_key_set(pg: Session, model: type[T], key_func: Callable[[T], tuple[Any, ...]]) -> set[tuple[Any, ...]]:
    return {key_func(row) for row in pg.scalars(select(model)).all()}


def migrate_related_table(
    sqlite_conn: sqlite3.Connection,
    pg: Session,
    table: str,
    model: type[Any],
    id_map: dict[int, int],
    key_func: Callable[[Any], tuple[Any, ...]],
    dry_run: bool,
) -> dict[str, int]:
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    seen_keys: set[tuple[Any, ...]] = set() if dry_run else existing_key_set(pg, model, key_func)
    pending = 0

    for row in sqlite_rows(sqlite_conn, table):
        payload = build_payload(model, row)
        if "game_id" in payload:
            old_game_id = row.get("game_id")
            new_game_id = id_map.get(int(old_game_id)) if old_game_id is not None else None
            if new_game_id is None:
                stats["skipped"] += 1
                continue
            payload["game_id"] = new_game_id

        if dry_run:
            stats["inserted"] += 1
            continue

        key = key_func(payload)
        if key in seen_keys:
            stats["skipped"] += 1
            continue

        pg.add(model(**payload))
        seen_keys.add(key)
        stats["inserted"] += 1
        pending += 1
        if pending >= 5000:
            pg.commit()
            pending = 0

    return stats


def print_counts(prefix: str, counts: dict[str, int]) -> None:
    print(prefix)
    for table in MIGRATED_TABLES:
        print(f"  {table}: {counts.get(table, 0)}")


def sqlite_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: sqlite_count(conn, table) for table in MIGRATED_TABLES}


def postgres_counts(pg: Session) -> dict[str, int]:
    return {
        "games": pg_count(pg, Game),
        "external_ids": pg_count(pg, ExternalId),
        "price_snapshots": pg_count(pg, PriceSnapshot),
        "rating_snapshots": pg_count(pg, RatingSnapshot),
        "source_snapshots": pg_count(pg, SourceSnapshot),
    }


def print_sample_games(pg: Session) -> None:
    print("Sample games:")
    for title in ("Baldur's Gate 3", "Elden Ring", "Hades"):
        game = pg.scalar(select(Game).where(func.lower(Game.title) == title.lower()).limit(1))
        if game:
            print(f"  FOUND {game.id}: {game.title} ({game.slug})")
        else:
            print(f"  MISSING: {title}")


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite)
    if not args.postgres_url.startswith("postgresql"):
        raise RuntimeError(f"Refusing to migrate into a non-PostgreSQL URL: {args.postgres_url}")

    sqlite_conn = sqlite_connect(sqlite_path)
    pg_engine = create_engine(args.postgres_url, pool_pre_ping=True)
    Base.metadata.create_all(pg_engine)
    SessionLocal = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)

    with SessionLocal() as pg:
        print_counts("SQLite counts before migration:", sqlite_counts(sqlite_conn))
        print_counts("PostgreSQL counts before migration:", postgres_counts(pg))

        id_map, game_stats = migrate_games(sqlite_conn, pg, dry_run=args.dry_run)
        print(f"games migration: {game_stats}")

        related_jobs = [
            ("external_ids", ExternalId, external_id_key),
            ("price_snapshots", PriceSnapshot, price_snapshot_key),
            ("rating_snapshots", RatingSnapshot, rating_snapshot_key),
            ("source_snapshots", SourceSnapshot, source_snapshot_key),
        ]
        for table, model, key_func in related_jobs:
            if not sqlite_table_exists(sqlite_conn, table):
                print(f"{table} migration: table missing, skipped")
                continue
            stats = migrate_related_table(sqlite_conn, pg, table, model, id_map, key_func, dry_run=args.dry_run)
            print(f"{table} migration: {stats}")

        if args.dry_run:
            pg.rollback()
            print("Dry run complete; no PostgreSQL changes were committed.")
        else:
            pg.commit()
            print("Migration committed.")

        print_counts("PostgreSQL counts after migration:", postgres_counts(pg))
        print_sample_games(pg)

    sqlite_conn.close()


if __name__ == "__main__":
    main()
