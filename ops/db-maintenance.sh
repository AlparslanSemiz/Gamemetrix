#!/usr/bin/env bash
# MANUAL database maintenance for GameMetrix. Never run from cron.
#
# VACUUM FULL rewrites a table and takes an ACCESS EXCLUSIVE lock: the table is unreadable
# and unwritable while it runs, and it needs free disk equal to the table's size. Run it
# once, in a quiet window, AFTER the 20261119_0023 migration has trimmed the data:
#
#   1. fresh backup:   ops/backup-db.sh
#   2. stop writers:   docker compose stop backend      (visitors see 502 meanwhile)
#   3. run:            ops/db-maintenance.sh
#   4. start again:    docker compose start backend
#
# Tables: external_ids (24 MB bloat), api_request_windows (rows purged), data_fill_runs
# (13 MB of rewritten JSON), games is NOT touched (largest, hot - repack separately).
# The partitioned snapshot tables need no VACUUM FULL: the retention job DROPs whole partitions.
#
# Usage: ops/db-maintenance.sh [--dry-run]
set -Eeuo pipefail

DB_CONTAINER="${DB_CONTAINER:-gamemetrix-db}"
TABLES=(external_ids api_request_windows data_fill_runs api_request_budgets)

psql_db() { docker exec -i "$DB_CONTAINER" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' "$@"; }

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "Would VACUUM (FULL, ANALYZE) in $DB_CONTAINER: ${TABLES[*]}"
  exit 0
fi

echo "Sizes before:"
psql_db <<'SQL'
SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) AS size
FROM pg_class WHERE relkind IN ('r','p') AND relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;
SQL

for table in "${TABLES[@]}"; do
  echo "VACUUM (FULL, ANALYZE) $table ..."
  echo "VACUUM (FULL, ANALYZE) $table;" | psql_db
done

echo "ANALYZE (whole database) ..."
echo "ANALYZE;" | psql_db

echo "Sizes after:"
psql_db <<'SQL'
SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) AS size
FROM pg_class WHERE relkind IN ('r','p') AND relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;
SQL
