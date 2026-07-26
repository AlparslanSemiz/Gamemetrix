#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root so production secret files remain root-owned." >&2
  exit 2
fi

repo_dir="${1:-/home/ubuntu/gamemetrix/Gamemetrix}"
repo_dir="$(realpath "$repo_dir")"
if [[ ! -f "$repo_dir/docker-compose.yml" || ! -f "$repo_dir/backend/.env" ]]; then
  echo "GameMetrix repository or backend/.env was not found at $repo_dir." >&2
  exit 2
fi
cd "$repo_dir"

read_env() {
  local file="$1" key="$2" line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s' "${line#*=}"
      return 0
    fi
  done < "$file"
  return 1
}

write_env() {
  local file="$1" key="$2" value="$3" line found=0
  local temporary
  temporary="$(mktemp "${file}.tmp.XXXXXX")"
  chmod 600 "$temporary"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s=%s\n' "$key" "$value" >> "$temporary"
      found=1
    else
      printf '%s\n' "$line" >> "$temporary"
    fi
  done < "$file"
  if [[ "$found" -eq 0 ]]; then
    printf '%s=%s\n' "$key" "$value" >> "$temporary"
  fi
  chown root:root "$temporary"
  mv -f "$temporary" "$file"
}

random_secret() {
  openssl rand -hex 32
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/var/backups/gamemetrix/security-rollout-$timestamp"
install -d -o root -g root -m 700 "$backup_dir"
install -o root -g root -m 600 .env "$backup_dir/root.env.before"
install -o root -g root -m 600 backend/.env "$backup_dir/backend.env.before"
chown root:root .env backend/.env
chmod 600 .env backend/.env

admin_user="$(read_env .env POSTGRES_USER)"
database_name="$(read_env .env POSTGRES_DB || printf gamemetrix)"
app_user="gamemetrix_app"
app_password="$(random_secret)"
if [[ ! "$admin_user" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "POSTGRES_USER is not a safe PostgreSQL identifier." >&2
  exit 2
fi
if [[ ! "$database_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "POSTGRES_DB is not a safe PostgreSQL identifier." >&2
  exit 2
fi

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$admin_user" -d "$database_name" <<SQL
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  '$app_user',
  '$app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$app_user')
\gexec
SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  '$app_user',
  '$app_password'
)
\gexec
SELECT format('REASSIGN OWNED BY %I TO %I', '$admin_user', '$app_user')
WHERE '$admin_user' <> '$app_user'
\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', '$database_name', '$app_user')
\gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', '$app_user')
\gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL

write_env .env ENV production
write_env .env APP_DB_USER "$app_user"
write_env .env APP_DB_PASSWORD "$app_password"

write_env backend/.env ENV production
write_env backend/.env ACCOUNT_AUTH_ENABLED false
write_env backend/.env ACCOUNT_BASE_URL https://gamemetrix.me
write_env backend/.env JWT_ISSUER gamemetrix-api
write_env backend/.env JWT_AUDIENCE gamemetrix-admin
write_env backend/.env CORS_ALLOW_ORIGINS https://gamemetrix.me,https://www.gamemetrix.me
write_env backend/.env AI_MAX_CONCURRENCY 2
write_env backend/.env AI_MAX_PROMPT_CHARS 16000
write_env backend/.env AI_MAX_OUTPUT_TOKENS 1024
write_env backend/.env GROQ_DAILY_LIMIT 1000
write_env backend/.env GROQ_DAILY_TOKEN_LIMIT 200000
write_env backend/.env GEMINI_DAILY_LIMIT 100
write_env backend/.env GEMINI_DAILY_TOKEN_LIMIT 100000
write_env backend/.env CLOUDFLARE_AI_DAILY_LIMIT 100
write_env backend/.env CLOUDFLARE_AI_DAILY_TOKEN_LIMIT 100000
write_env backend/.env OPENROUTER_DAILY_LIMIT 50
write_env backend/.env OPENROUTER_DAILY_TOKEN_LIMIT 100000
write_env backend/.env SIMILARITY_USE_AI false
write_env backend/.env SIMILARITY_AI_DAILY_LIMIT 25
write_env backend/.env SIMILARITY_AI_MIN_INTERVAL_SECONDS 2

docker compose config --quiet
docker compose build backend frontend
docker compose up -d --wait --wait-timeout 240
curl --fail --silent --show-error --max-time 15 \
  -H "Host: api.gamemetrix.me" \
  -H "X-Forwarded-Proto: https" \
  http://127.0.0.1/health >/dev/null

admin_password="$(random_secret)"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$admin_user" -d "$database_name" <<SQL
SELECT format('ALTER ROLE %I WITH PASSWORD %L', '$admin_user', '$admin_password')
\gexec
SQL
write_env .env POSTGRES_PASSWORD "$admin_password"
install -o root -g root -m 600 .env "$backup_dir/root.env.after"

role_flags="$(
  docker compose exec -T backend python - <<'PY'
from sqlalchemy import text
from app.database import engine

with engine.connect() as connection:
    row = connection.execute(
        text(
            "select rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "from pg_roles where rolname=current_user"
        )
    ).one()
print(",".join(str(value).lower() for value in row))
PY
)"
if [[ "$role_flags" != "false,false,false,false,false" ]]; then
  echo "Application database role still has elevated cluster privileges." >&2
  exit 1
fi

echo "Production foundation deployed successfully."
echo "Secure rollback material: $backup_dir"
echo "Origin TLS and Cloudflare-only UFW remain pending the Origin CA files."
