# Production security rollout

This runbook is intentionally ordered so origin TLS is healthy before direct
origin access is blocked. Keep two authenticated SSH sessions open throughout
the TLS and firewall stages.

## Preconditions

- Take an encrypted PostgreSQL dump and verify that it can be listed.
- Keep the previous application images and a root-owned, mode `600` environment
  backup for the rollback window.
- In Cloudflare, create an Origin CA certificate covering `gamemetrix.me` and
  `*.gamemetrix.me`. Never store its private key in Git, a ticket, or chat.
- Securely upload the certificate and key to
  `/etc/gamemetrix/origin-tls/origin.crt` and
  `/etc/gamemetrix/origin-tls/origin.key`. Use owner `root`, group `101`, mode
  `0644` for the certificate and `0640` for the key so the non-root nginx
  process can read it.

## Required production environment

The root `.env` must be mode `600` and contain distinct database administrator
and application credentials:

```text
ENV=production
POSTGRES_USER=gamemetrix
POSTGRES_PASSWORD=<rotated-admin-password>
POSTGRES_DB=gamemetrix
APP_DB_USER=gamemetrix_app
APP_DB_PASSWORD=<distinct-random-url-safe-password>
ORIGIN_CERT_PATH=/etc/gamemetrix/origin-tls/origin.crt
ORIGIN_KEY_PATH=/etc/gamemetrix/origin-tls/origin.key
```

Until SMTP is configured and verification/reset delivery has been tested,
`backend/.env` must include:

```text
ENV=production
ACCOUNT_AUTH_ENABLED=false
ACCOUNT_BASE_URL=https://gamemetrix.me
JWT_ISSUER=gamemetrix-api
JWT_AUDIENCE=gamemetrix-admin
CORS_ALLOW_ORIGINS=https://gamemetrix.me,https://www.gamemetrix.me
```

The application refuses invalid production settings. Do not work around that
validator.

## Database role migration

Export the protected `.env` values into a root shell, then run
`ops/create-app-db-role.sql` with `psql` variables `admin_user`, `app_user`,
`app_password`, and `database_name`. The SQL is idempotent. Verify the final
row reports `false` for superuser, create database, create role, replication,
and bypass-RLS.

After deployment, verify from the backend container:

```bash
docker compose exec -T backend python -c \
  "from sqlalchemy import text; from app.database import engine; print(engine.connect().execute(text(\"select current_user, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls from pg_roles where rolname=current_user\")).one())"
```

All Boolean role flags must be false. Alembic still works because the
application role owns the application database/schema; it is not a cluster
superuser.

For the current zero-user/no-SMTP rollout, the repository also provides one
idempotent foundation command. It creates secure backups, migrates the
application role, writes the fail-closed production/account-disabled settings,
builds and health-checks the hardened containers, rotates the administrator
database password only after health is green, and verifies the backend role:

```bash
sudo bash ops/deploy-production-foundation.sh
```

It deliberately does not enable origin TLS, Full (strict), UFW, upgrades, or a
reboot; those remain ordered manual stages because the certificate and a second
SSH session are external safety prerequisites.

## Routine deployment

Production environment files remain root-owned mode `600`; the unprivileged SSH
user must never be granted read access to them. Routine deployments therefore use
the root-only wrapper after the developer has pushed `main`:

```bash
sudo -n bash /home/ubuntu/gamemetrix/Gamemetrix/ops/deploy-production.sh
```

The script pulls Git as the unprivileged `ubuntu` owner, validates the protected
file boundary and Compose configuration as root, builds the application images,
waits for every service health check, and verifies the internal API before
reporting success. If Origin CA files are present, it automatically includes the
production TLS overlay.

## Origin TLS and Cloudflare

Validate and deploy the production overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
docker compose ps
curl --resolve gamemetrix.me:443:127.0.0.1 https://gamemetrix.me/health
```

Only after that origin HTTPS check succeeds, switch Cloudflare SSL/TLS mode to
**Full (strict)**. Confirm the public site and API health through Cloudflare,
then leave them under observation before changing the firewall.

## Cloudflare-only firewall

From the second SSH session, review and run:

```bash
sudo bash ops/configure-cloudflare-ufw.sh --apply
```

The script downloads and validates Cloudflare's current official IPv4/IPv6
ranges over HTTPS, adds SSH protection first, adds source-specific 80/443
rules, removes only broad web allows, and stores `ufw show added` under
`/var/backups/gamemetrix/`.

Verify that the public domains still work through Cloudflare and that direct
origin IPv4/IPv6 connections to 80/443 fail. If SSH or health checks regress,
use the already-open second session and the saved UFW rule list to roll back.

## Updates and observation

Apply Ubuntu security updates, inspect services requiring restart, and schedule
the reboot only after application/database health is green. After reboot,
observe container health, OOM events, application errors, AI quota rows, and
authentication logs for at least 15 minutes.

Account authentication may be enabled only after production SMTP credentials
are installed and real verification and password-reset messages have completed
end to end.
