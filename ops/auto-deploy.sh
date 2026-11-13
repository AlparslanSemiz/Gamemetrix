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
set -Eeuo pipefail

repo_dir="${REPO_DIR:-/home/ubuntu/gamemetrix/Gamemetrix}"
git_user="${DEPLOY_GIT_USER:-ubuntu}"
cd "$repo_dir"

log() { echo "[gamemetrix-autodeploy] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

prefix="$(sed -n 's/^GAMEMETRIX_IMAGE_PREFIX=//p' .env | tail -1)"
[[ -n "$prefix" ]] || exit 0

sudo -u "$git_user" git fetch --quiet origin main
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse origin/main)"
[[ "$local_sha" != "$remote_sha" ]] || exit 0

for svc in backend frontend; do
  if ! docker manifest inspect "$prefix-$svc:sha-$remote_sha" >/dev/null 2>&1; then
    exit 0   # CI hasn't published this commit yet; try again next run
  fi
done

log "deploying ${remote_sha:0:7} (was ${local_sha:0:7})"
if "$repo_dir/ops/deploy-production.sh" "$repo_dir"; then
  log "deployed ${remote_sha:0:7}"
else
  log "deploy of ${remote_sha:0:7} FAILED (exit $?)"
fi
