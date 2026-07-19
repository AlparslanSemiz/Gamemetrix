#!/usr/bin/env bash
# GameMetrix disk/cache cleanup — meant to run daily via cron on the 1GB/30GB VM.
#
# Safe-by-default policy:
#   - Things that are purely reconstructable (docker build cache, dangling
#     images/containers, page cache, journal logs) are deleted automatically.
#   - Things that are data (old legacy DB backup snapshots) are only REPORTED by
#     default; deletion requires an explicit opt-in env var, because an
#     unattended cron job should never be the thing that silently destroys
#     your last good backup.
#
# Install:
#   chmod +x ops/cleanup.sh
#   sudo crontab -e
#   0 3 * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/cleanup.sh >> /var/log/gamemetrix-cleanup.log 2>&1
set -euo pipefail

PROJECT_DIR="/home/ubuntu/gamemetrix/Gamemetrix"
LOCK_FILE="/tmp/gamemetrix-cleanup.lock"
LOG_TAG="[gamemetrix-cleanup]"

# App log files that are known to grow unbounded outside Docker's own log
# rotation (e.g. left over from running uvicorn directly, not via compose).
APP_LOG_GLOBS=(
  "$PROJECT_DIR/backend/.uvicorn.current.out.log"
  "$PROJECT_DIR/backend/.uvicorn.current.err.log"
  "$PROJECT_DIR/backend/.uvicorn.out.log"
  "$PROJECT_DIR/backend/.uvicorn.err.log"
)
LOG_TRUNCATE_THRESHOLD_BYTES=$((20 * 1024 * 1024)) # 20MB
LOG_TAIL_KEEP_BYTES=$((1 * 1024 * 1024))           # keep the last 1MB on rotation

# Old legacy DB backup snapshots —
# reported only, unless explicitly enabled.
BACKUP_MAX_AGE_DAYS=14
AUTO_DELETE_OLD_BACKUPS="${AUTO_DELETE_OLD_BACKUPS:-false}"

log() { echo "$LOG_TAG $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# ── Prevent overlapping runs (e.g. a previous run still doing a big docker
#    prune when the next 03:00 cron fires) ───────────────────────────────────
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "another cleanup run is already in progress — exiting"
  exit 0
fi

log "=== starting cleanup ==="

# ── 1. Docker: remove dangling images, stopped containers, unused networks,
#    and the build cache. None of this touches named volumes (pgdata is
#    safe) or images currently used by a running container. ─────────────────
if command -v docker >/dev/null 2>&1; then
  log "docker system prune (dangling images/containers/networks)"
  docker system prune -f --filter "until=24h" || log "docker system prune failed (continuing)"

  log "docker builder prune (stale build cache)"
  docker builder prune -f --filter "until=72h" || log "docker builder prune failed (continuing)"
else
  log "docker not found — skipping docker cleanup"
fi

# ── 2. Rotate known app log files (copytruncate style: keep the tail, zero
#    the rest) so a single runaway log can't fill the 30GB disk. Docker
#    container logs are already capped via docker-compose.yml's
#    logging.options.max-size, so this only targets non-container log files. ─
for f in "${APP_LOG_GLOBS[@]}"; do
  [ -f "$f" ] || continue
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$size" -gt "$LOG_TRUNCATE_THRESHOLD_BYTES" ]; then
    log "rotating $f (${size} bytes)"
    tail -c "$LOG_TAIL_KEEP_BYTES" "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
  fi
done

# ── 3. System journal — cap to 100MB total, independent of app logs ─────────
if command -v journalctl >/dev/null 2>&1; then
  log "vacuuming systemd journal to 100M"
  journalctl --vacuum-size=100M >/dev/null 2>&1 || true
fi

# ── 4. Page cache: safe to drop (kernel reclaims it on demand anyway), but
#    genuinely optional — this does NOT free memory held by application
#    processes and rarely moves the needle on a box this tight. Included
#    because it was asked for; comment out if you'd rather leave it alone. ──
if [ -w /proc/sys/vm/drop_caches ]; then
  sync
  echo 1 > /proc/sys/vm/drop_caches 2>/dev/null || log "drop_caches needs root — skipped"
fi

# ── 5. Old legacy DB backup snapshots — report, don't auto-delete ───────────
shopt -s nullglob
old_backups=("$PROJECT_DIR"/backend/*.db.*.bak)
shopt -u nullglob
for bak in "${old_backups[@]:-}"; do
  [ -f "$bak" ] || continue
  age_days=$(( ( $(date +%s) - $(stat -c%Y "$bak") ) / 86400 ))
  size_h=$(du -h "$bak" | cut -f1)
  if [ "$age_days" -ge "$BACKUP_MAX_AGE_DAYS" ]; then
    if [ "$AUTO_DELETE_OLD_BACKUPS" = "true" ]; then
      log "deleting old backup $bak (${size_h}, ${age_days}d old) — AUTO_DELETE_OLD_BACKUPS=true"
      rm -f "$bak"
    else
      log "REPORT: $bak is ${size_h} and ${age_days}d old — set AUTO_DELETE_OLD_BACKUPS=true to auto-remove"
    fi
  fi
done

log "disk usage after cleanup:"
df -h / | tee -a /dev/stderr

log "=== cleanup finished ==="
