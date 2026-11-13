#!/usr/bin/env bash
# Nightly PostgreSQL backup for GameMetrix.
#
# Writes a compressed pg_dump (custom format) of the catalog, checks that it can
# be read back, keeps the last $KEEP_DAYS days and, if BACKUP_REMOTE is set,
# copies it to a second machine so a lost VM does not mean a lost database.
#
# Install (as root):
#   chmod +x ops/backup-db.sh
#   crontab -e
#   30 3 * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/backup-db.sh >> /var/log/gamemetrix-backup.log 2>&1
#
# Optional off-site copy (rsync over SSH, e.g. to the backup VM via Tailscale):
#   BACKUP_REMOTE=backup@gm-backup:/srv/backups/gamemetrix
#
# Restore:
#   docker exec -i gamemetrix-db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < FILE.dump
set -Eeuo pipefail

DB_CONTAINER="${DB_CONTAINER:-gamemetrix-db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/gamemetrix}"
KEEP_DAYS="${KEEP_DAYS:-14}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
LOG_TAG="[gamemetrix-backup]"

log() { echo "$LOG_TAG $(date '+%Y-%m-%d %H:%M:%S') $*"; }
trap 'log "FAILED at line $LINENO"' ERR

exec 9>/tmp/gamemetrix-backup.lock
if ! flock -n 9; then
  log "another backup is still running, exiting"
  exit 0
fi

umask 077
mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/gamemetrix-$(date '+%Y%m%d-%H%M').dump"
tmp="$file.partial"

log "dumping database from $DB_CONTAINER"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6' > "$tmp"

# A truncated or empty dump must never replace a good one.
if [[ ! -s "$tmp" ]]; then
  log "dump is empty"
  rm -f "$tmp"
  exit 1
fi
tables=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$tmp" | grep -c ' TABLE DATA ' || true)
if [[ "$tables" -lt 1 ]]; then
  log "dump has no table data, keeping it as $tmp for inspection"
  exit 1
fi
mv "$tmp" "$file"
log "wrote $file ($(du -h "$file" | cut -f1), $tables tables)"

find "$BACKUP_DIR" -name 'gamemetrix-*.dump' -mtime +"$KEEP_DAYS" -print -delete | sed "s/^/$LOG_TAG removed /"

if [[ -n "$BACKUP_REMOTE" ]]; then
  log "copying to $BACKUP_REMOTE"
  rsync -a --delete --include 'gamemetrix-*.dump' --exclude '*' "$BACKUP_DIR/" "$BACKUP_REMOTE/"
fi

log "done"
