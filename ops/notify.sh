#!/usr/bin/env bash
# Tiny notification helper for the ops scripts. Never fails its caller.
#
#   ops/notify.sh "deploy of abc1234 failed"   POST the message to NOTIFY_URL
#   ops/notify.sh --ping backup                GET $NOTIFY_PING_URL/backup  (dead-man's switch)
#
# Settings come from /etc/gamemetrix/notify.env (override with NOTIFY_ENV_FILE), root-owned,
# mode 600, for example:
#   NOTIFY_URL=https://discord.com/api/webhooks/<id>/<token>   # or Slack/any JSON webhook
#   NOTIFY_PING_URL=https://hc-ping.com/<project-ping-key>     # Healthchecks.io slug pings
# NOTIFY_FORMAT=text sends the bare message instead of {"content": "...", "text": "..."}
# (for ntfy.sh and similar). If the file or the variable is missing this does nothing, so
# the scripts work the same on a host that has no notification channel yet.
set -u

env_file="${NOTIFY_ENV_FILE:-/etc/gamemetrix/notify.env}"
if [[ -r "$env_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
fi

host="$(hostname -s 2>/dev/null || echo gamemetrix)"

if [[ "${1:-}" == "--ping" ]]; then
  name="${2:-}"
  [[ -n "${NOTIFY_PING_URL:-}" && -n "$name" ]] || exit 0
  curl -fsS -m 10 --retry 2 -o /dev/null "${NOTIFY_PING_URL%/}/$name" 2>/dev/null || true
  exit 0
fi

message="${1:-}"
[[ -n "${NOTIFY_URL:-}" && -n "$message" ]] || exit 0
message="[$host] $message"

if [[ "${NOTIFY_FORMAT:-json}" == "text" ]]; then
  curl -fsS -m 10 -o /dev/null -X POST --data-binary "$message" "$NOTIFY_URL" 2>/dev/null || true
else
  # Escape backslashes, quotes and newlines for a one-field JSON body without needing jq.
  escaped="${message//\\/\\\\}"
  escaped="${escaped//\"/\\\"}"
  escaped="${escaped//$'\n'/\\n}"
  curl -fsS -m 10 -o /dev/null -X POST -H 'Content-Type: application/json' \
    --data "{\"content\":\"$escaped\",\"text\":\"$escaped\"}" "$NOTIFY_URL" 2>/dev/null || true
fi
exit 0
