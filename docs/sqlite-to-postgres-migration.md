# SQLite to PostgreSQL Migration

Use this when recovering the legacy local SQLite catalog into the Docker Compose PostgreSQL database.

The migration is idempotent and does not truncate/drop PostgreSQL tables. It matches games by `slug`, remaps old SQLite `game_id` values to PostgreSQL game IDs, and upserts related rows for:

- `games`
- `external_ids`
- `price_snapshots`
- `rating_snapshots`
- `source_snapshots`

## Preconditions

Production Docker Compose should point the backend at PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://admin:password123@db:5432/gamemetrix
```

The SQLite file should exist on the host at:

```text
backend/gamemetrix.dev.db
```

## Dry Run

```bash
docker compose build backend
docker compose run --rm \
  -v "$PWD/backend/gamemetrix.dev.db:/tmp/gamemetrix.dev.db:ro" \
  backend \
  python scripts/migrate_sqlite_to_postgres.py --sqlite /tmp/gamemetrix.dev.db --dry-run
```

## Apply Migration

```bash
docker compose build backend
docker compose run --rm \
  -v "$PWD/backend/gamemetrix.dev.db:/tmp/gamemetrix.dev.db:ro" \
  backend \
  python scripts/migrate_sqlite_to_postgres.py --sqlite /tmp/gamemetrix.dev.db
```

The script prints SQLite counts, PostgreSQL counts before and after, and sample lookups for Baldur's Gate 3, Elden Ring, and Hades.

After migration:

```bash
docker compose up -d --build backend
docker compose restart nginx
curl 'http://gamemetrix.me/api/games?limit=1&offset=0'
```
