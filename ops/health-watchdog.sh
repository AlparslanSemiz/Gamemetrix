#!/usr/bin/env bash
# GameMetrix health watchdog: brings missing, stopped or stuck containers back.
#
# `restart: always` only covers a container that crashes. It does nothing when a
# container was removed (for example by a deploy that failed halfway) or when it
# keeps running but stays unhealthy. This script covers those cases.
#
# Every run, for each service:
#   - container missing or not running  -> `docker compose up -d --no-build <svc>`
#   - unhealthy for UNHEALTHY_LIMIT runs  -> `docker restart <container>`
# It never builds images and skips the run while a deploy holds the deploy lock.
#
# Install (as root, every minute):
#   chmod +x ops/health-watchdog.sh
#   crontab -e
#   * * * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/health-watchdog.sh >> /var/log/gamemetrix-watchdog.log 2>&1
set -Eeuo pipefail

REPO_DIR="${REPO_DIR:-/home/ubuntu/gamemetrix/Gamemetrix}"
STATE_DIR="${STATE_DIR:-/var/lib/gamemetrix-watchdog}"
LOG_FILE="${LOG_FILE:-/var/log/gamemetrix-watchdog.log}"
UNHEALTHY_LIMIT="${UNHEALTHY_LIMIT:-3}"
SERVICES=(db backend frontend nginx)

log() { echo "[gamemetrix-watchdog] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# A deploy is recreating containers on purpose; stay out of its way.
exec 8>/tmp/gamemetrix-production-deploy.lock
flock -n 8 || exit 0
# Never run two watchdogs at once.
exec 9>/tmp/gamemetrix-watchdog.lock
flock -n 9 || exit 0

# Keep the log small.
if [[ -f "$LOG_FILE" ]] && (( $(stat -c%s "$LOG_FILE") > 5 * 1024 * 1024 )); then
  tail -c $((512 * 1024)) "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

mkdir -p "$STATE_DIR"
cd "$REPO_DIR"

compose=(docker compose -f docker-compose.yml)
if [[ -s /etc/gamemetrix/origin-tls/origin.crt && -s /etc/gamemetrix/origin-tls/origin.key ]]; then
  compose+=(-f docker-compose.production.yml)
fi

for svc in "${SERVICES[@]}"; do
  name="gamemetrix-$svc"
  status="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo none)"
  counter="$STATE_DIR/$svc.unhealthy"

  if [[ "$status" != "running" ]]; then
    log "$name is $status, starting it"
    "${compose[@]}" up -d --no-build "$svc" >/dev/null 2>&1 || log "$name: compose up failed"
    rm -f "$counter"
    continue
  fi

  if [[ "$health" == "unhealthy" ]]; then
    n=$(( $(cat "$counter" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$counter"
    if (( n >= UNHEALTHY_LIMIT )); then
      log "$name unhealthy for $n checks, restarting it"
      docker restart "$name" >/dev/null || log "$name: restart failed"
      rm -f "$counter"
    fi
  else
    rm -f "$counter"
  fi
done
