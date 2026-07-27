#!/usr/bin/env bash
set -Eeuo pipefail

trap 'echo "Production deployment failed at line $LINENO." >&2' ERR

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this deployment as root so protected environment files remain unreadable to the deploy user." >&2
  exit 2
fi

# Docker Compose recreate operations are not safe to overlap: a second deploy
# can race the temporary rename of the current container and fail with a
# "<container-id>_gamemetrix-backend is already in use" conflict. Serialize the
# complete rollout and allow an interactive deploy to wait for an active one.
exec 9>/tmp/gamemetrix-production-deploy.lock
if ! flock -w 900 9; then
  echo "Another production deployment did not finish within 15 minutes." >&2
  exit 75
fi

repo_dir="${1:-/home/ubuntu/gamemetrix/Gamemetrix}"
git_user="${DEPLOY_GIT_USER:-ubuntu}"
repo_dir="$(realpath "$repo_dir")"

if [[ ! -f "$repo_dir/docker-compose.yml" || ! -f "$repo_dir/.env" ]]; then
  echo "GameMetrix repository or root .env was not found at $repo_dir." >&2
  exit 2
fi

cd "$repo_dir"

echo ">>> Git pull..."
sudo -u "$git_user" git pull --ff-only origin main

for secret_file in .env backend/.env; do
  if [[ "$(stat -c '%a:%U:%G' "$secret_file")" != "600:root:root" ]]; then
    echo "Refusing deployment: $secret_file must be root:root mode 600." >&2
    exit 2
  fi
done

compose=(docker compose -f docker-compose.yml)
origin_cert="/etc/gamemetrix/origin-tls/origin.crt"
origin_key="/etc/gamemetrix/origin-tls/origin.key"
if [[ -s "$origin_cert" && -s "$origin_key" ]]; then
  compose+=(-f docker-compose.production.yml)
  echo ">>> Origin TLS overlay enabled."
else
  echo ">>> Origin TLS material is absent; deploying the HTTP foundation only."
fi

echo ">>> Compose configuration check..."
"${compose[@]}" config --quiet

echo ">>> Docker build & health-checked rollout..."
"${compose[@]}" build backend frontend
# Compose can retain a stale dependency container ID when backend and frontend
# are both recreated in one `up --wait` operation while nginx is still running.
# Start each dependency layer deterministically before checking the next one.
"${compose[@]}" up -d --wait --wait-timeout 240 db backend
"${compose[@]}" up -d --wait --wait-timeout 240 frontend
"${compose[@]}" up -d --wait --wait-timeout 240 nginx

curl --fail --silent --show-error --max-time 15 \
  -H "Host: api.gamemetrix.me" \
  -H "X-Forwarded-Proto: https" \
  http://127.0.0.1/health >/dev/null

echo ">>> Deployment completed successfully."
"${compose[@]}" ps
