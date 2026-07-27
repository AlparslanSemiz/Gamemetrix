#!/usr/bin/env bash
# GameMetrix disk/cache cleanup — meant to run daily via cron on the 1GB/30GB VM.
#
# Safe-by-default policy:
#   - Things that are purely reconstructable (docker build cache, dangling
#     images/containers, journal logs) are deleted automatically.
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

# ── 4. Page cache: keep it by default. Dropping it does not reduce application
#    RSS and makes PostgreSQL reread hot data from disk. It remains available as
#    an explicit emergency-only option: DROP_PAGE_CACHE=true ./ops/cleanup.sh. ─
if [ "${DROP_PAGE_CACHE:-false}" = "true" ] && [ -w /proc/sys/vm/drop_caches ]; then
  sync
  echo 1 > /proc/sys/vm/drop_caches 2>/dev/null || log "drop_caches needs root — skipped"
fi

log "disk usage after cleanup:"
df -h / | tee -a /dev/stderr

log "=== cleanup finished ==="
