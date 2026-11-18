#!/usr/bin/env bash
# Deploys main automatically once CI has published its images.
#
# Every run: fetch origin/main; if it is ahead of what is checked out and both images
# for that commit exist in the registry, run ops/deploy-production.sh. So merging a PR
# is the whole deployment: CI builds (~5 min), this picks it up within 5 more minutes.
# Only active when GAMEMETRIX_IMAGE_PREFIX is set in .env (registry mode).
#
# Install (as root, every 5 minutes):
#   */5 * * * * /home/ubuntu/gamemetrix/Gamemetrix/ops/auto-deploy.sh >> /var/log/gamemetrix-autodeploy.log 2>&1
#
# "Deployed" is tracked in .deployed-sha, written by ops/deploy-production.sh only after a
# deploy succeeded. Comparing against the checkout instead (git HEAD) was wrong: the deploy
# script pulls first, so a deploy that failed after the pull looked finished and was never
# retried. A failure is reported through ops/notify.sh once per commit, not every 5 minutes.
set -Eeuo pipefail

repo_dir="${REPO_DIR:-/home/ubuntu/gamemetrix/Gamemetrix}"
git_user="${DEPLOY_GIT_USER:-ubuntu}"
cd "$repo_dir"

# This runs as root but the checkout belongs to ubuntu, so git refuses it ("dubious
# ownership") unless told otherwise. Per-process config, nothing written to disk.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$repo_dir"

notify="$repo_dir/ops/notify.sh"
deployed_file="$repo_dir/.deployed-sha"
notified_file="$repo_dir/.deploy-failure-notified"

log() { echo "[gamemetrix-autodeploy] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# Tell the operator once per distinct failure key (a sha, or a crash location).
notify_once() {
  local key="$1" message="$2"
  [[ "$(cat "$notified_file" 2>/dev/null || true)" == "$key" ]] && return 0
  echo "$key" > "$notified_file"
  "$notify" "$message" || true
}

trap 'rc=$?; log "crashed at line $LINENO (exit $rc)"; notify_once "crash-$LINENO" "auto-deploy crashed at line $LINENO (exit $rc); see /var/log/gamemetrix-autodeploy.log"' ERR

prefix="$(sed -n 's/^GAMEMETRIX_IMAGE_PREFIX=//p' .env | tail -1)"
[[ -n "$prefix" ]] || exit 0

sudo -u "$git_user" git fetch --quiet origin main
deployed_sha="$(cat "$deployed_file" 2>/dev/null || true)"
remote_sha="$(git rev-parse origin/main)"
[[ "$deployed_sha" != "$remote_sha" ]] || exit 0

for svc in backend frontend; do
  if ! docker manifest inspect "$prefix-$svc:sha-$remote_sha" >/dev/null 2>&1; then
    exit 0   # CI hasn't published this commit yet; try again next run
  fi
done

log "deploying ${remote_sha:0:7} (was ${deployed_sha:0:7})"
if "$repo_dir/ops/deploy-production.sh" "$repo_dir"; then
  log "deployed ${remote_sha:0:7}"
  rm -f "$notified_file"
  "$notify" "deployed ${remote_sha:0:7}" || true
else
  rc=$?
  log "deploy of ${remote_sha:0:7} FAILED (exit $rc); will retry on the next run"
  notify_once "$remote_sha" "deploy of ${remote_sha:0:7} FAILED (exit $rc); it is retried every 5 minutes. Log: /var/log/gamemetrix-autodeploy.log"
fi
