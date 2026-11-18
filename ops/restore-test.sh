#!/usr/bin/env bash
# Proves the newest nightly backup can actually be restored.
#
# A backup nobody has restored is only a hope. This loads the latest dump from
# $BACKUP_DIR into a throwaway postgres:15-alpine container (no published ports, its own
# anonymous volume, removed at the end), then checks that the catalog tables came back
# with a sane number of rows. It never touches the production database container.
#
# The host has 1 GB RAM, so the test container is capped at 160 MB; run it when traffic is
# low (monthly is enough):
#   sudo ops/restore-test.sh                 # newest dump in /var/backups/gamemetrix
#   sudo ops/restore-test.sh /path/to.dump   # a specific dump (for example one copied off-site)
# Optional cron, first Sunday of the month at 04:10:
#   10 4 1-7 * 0 /home/ubuntu/gamemetrix/Gamemetrix/ops/restore-test.sh >> /var/log/gamemetrix-restore-test.log 2>&1
#
# Exit status 0 = restored and plausible. Anything else sends ops/notify.sh a message.
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/gamemetrix}"
IMAGE="${RESTORE_TEST_IMAGE:-postgres:15-alpine}"
MIN_GAMES="${RESTORE_TEST_MIN_GAMES:-1000}"
CONTAINER="gamemetrix-restore-test-$$"
notify="$(dirname "$(readlink -f "$0")")/notify.sh"
LOG_TAG="[gamemetrix-restore-test]"

log() { echo "$LOG_TAG $(date '+%Y-%m-%d %H:%M:%S') $*"; }
cleanup() { docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true; }
fail() { log "FAILED: $*"; "$notify" "restore test FAILED: $*" || true; exit 1; }
trap cleanup EXIT
trap 'fail "error at line $LINENO"' ERR

dump="${1:-}"
if [[ -z "$dump" ]]; then
  dump="$(find "$BACKUP_DIR" -maxdepth 1 -name 'gamemetrix-*.dump' -print | sort | tail -1)"
fi
[[ -n "$dump" && -s "$dump" ]] || fail "no dump found in $BACKUP_DIR"
log "restoring $dump ($(du -h "$dump" | cut -f1))"

docker run -d --name "$CONTAINER" --memory 160m --memory-swap 320m \
  -e POSTGRES_PASSWORD=restore-test -e POSTGRES_DB=restore_test \
  "$IMAGE" postgres -c shared_buffers=32MB -c maintenance_work_mem=32MB -c fsync=off >/dev/null

ready=0
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U postgres -d restore_test >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[[ "$ready" == 1 ]] || fail "temporary postgres did not become ready"
# -h 127.0.0.1 matters: during first-run init the image runs a temporary server that listens
# on the unix socket only, so a TCP answer means the real server is up.

# --no-owner/--no-privileges: the dump was made by the application's role, which does not
# exist in this throwaway server. Warnings about missing roles are not data loss.
docker exec -i "$CONTAINER" pg_restore -U postgres -d restore_test --no-owner --no-privileges \
  < "$dump" || log "pg_restore reported warnings (checking the data anyway)"

count() { docker exec "$CONTAINER" psql -U postgres -d restore_test -At -c "SELECT count(*) FROM $1"; }

games="$(count games)"
log "games: $games"
for table in users account_sessions user_collections external_ids rating_snapshots price_snapshots; do
  if docker exec "$CONTAINER" psql -U postgres -d restore_test -At \
       -c "SELECT to_regclass('public.$table') IS NOT NULL" | grep -q t; then
    log "$table: $(count "$table")"
  fi
done
revision="$(docker exec "$CONTAINER" psql -U postgres -d restore_test -At -c 'SELECT version_num FROM alembic_version' || true)"
log "alembic revision: ${revision:-none}"

[[ "$games" -ge "$MIN_GAMES" ]] || fail "only $games games restored (expected at least $MIN_GAMES)"
[[ -n "$revision" ]] || fail "alembic_version is missing from the restore"

log "OK: backup $(basename "$dump") restores cleanly"
"$notify" --ping restore-test || true
