#!/usr/bin/env bash
# GameMetrix memory-leak watchdog — samples container RSS every run and
# restarts a container only after it's been sustained-high for several
# consecutive samples (avoids restarting on a normal transient spike, e.g.
# a big RAWG import or a Locust run).
#
# Install (every 5 minutes):
#   chmod +x ops/mem-watchdog.sh
#   crontab -e
#   */5 * * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/mem-watchdog.sh >> /var/log/gamemetrix-memwatch.log 2>&1
set -euo pipefail

LOG_FILE="/var/log/gamemetrix-memwatch.log"
STATE_DIR="/tmp/gamemetrix-memwatch"
mkdir -p "$STATE_DIR"

# Container -> mem_limit in MB (must match docker-compose.yml's mem_limit).
declare -A LIMITS_MB=(
  [gamemetrix-backend]=400
  [gamemetrix-db]=160
  [gamemetrix-frontend]=192
  [gamemetrix-nginx]=48
)
# Restart a container once it's stayed above this fraction of its limit for
# CONSECUTIVE_BREACH_LIMIT samples in a row (a real leak trend, not a blip).
WARN_THRESHOLD_PCT=85
CONSECUTIVE_BREACH_LIMIT=3

# Self-cap this log (cron output can grow just like anything else).
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt $((10 * 1024 * 1024)) ]; then
  tail -c $((1 * 1024 * 1024)) "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }

for name in "${!LIMITS_MB[@]}"; do
  if ! docker inspect "$name" >/dev/null 2>&1; then
    continue
  fi

  limit_mb="${LIMITS_MB[$name]}"
  usage_bytes=$(docker stats --no-stream --format '{{.MemUsage}}' "$name" | awk -F'/' '{print $1}')
  # docker stats prints values like "123.4MiB" or "12KiB" — normalize to MB.
  usage_mb=$(python3 - "$usage_bytes" <<'PY'
import sys
val = sys.argv[1].strip()
# Longest/most-specific suffix first — "MiB" also ends with "B".
units = [("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024), ("B", 1)]
for suffix, mult in units:
    if val.endswith(suffix):
        num = float(val[: -len(suffix)])
        print(round(num * mult / (1024**2), 1))
        break
else:
    print(0)
PY
)
  pct=$(python3 -c "print(round(${usage_mb} / ${limit_mb} * 100, 1))")

  state_file="$STATE_DIR/${name}.breach_count"
  breach_count=0
  [ -f "$state_file" ] && breach_count=$(cat "$state_file")

  echo "$(ts) $name: ${usage_mb}MB / ${limit_mb}MB (${pct}%)" >> "$LOG_FILE"

  if awk -v p="$pct" -v t="$WARN_THRESHOLD_PCT" 'BEGIN{exit !(p>=t)}'; then
    breach_count=$((breach_count + 1))
    echo "$(ts) $name: WARN — ${pct}% >= ${WARN_THRESHOLD_PCT}% (consecutive breach #${breach_count})" >> "$LOG_FILE"
    if [ "$breach_count" -ge "$CONSECUTIVE_BREACH_LIMIT" ]; then
      echo "$(ts) $name: sustained high memory for ${breach_count} samples — restarting container" >> "$LOG_FILE"
      docker restart "$name" >> "$LOG_FILE" 2>&1
      breach_count=0
    fi
  else
    breach_count=0
  fi
  echo "$breach_count" > "$state_file"
done
