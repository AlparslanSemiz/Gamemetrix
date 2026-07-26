GameMetrix
==========

GameMetrix is a game decision catalog with a FastAPI/PostgreSQL backend and a
React Router Framework Mode frontend. Public game and curation routes render on
the server; the catalog remains interactive after hydration.

## Run PostgreSQL

Copy `.env.example` to the gitignored root `.env` and replace its URL-safe
PostgreSQL password. Docker Compose loads these values automatically. For a
one-off shell session, the equivalent is:

```powershell
$env:POSTGRES_USER="gamemetrix"
$env:POSTGRES_PASSWORD="<choose-a-local-password>"
$env:POSTGRES_DB="gamemetrix"
$env:APP_DB_USER="gamemetrix_app"
$env:APP_DB_PASSWORD="<choose-a-different-local-password>"
$env:ENV="development"
docker compose up -d db
```

When the backend runs directly on Windows, set `backend\.env` with a matching
PostgreSQL database URL:

```text
DATABASE_URL=postgresql+psycopg://gamemetrix:<choose-a-local-password>@localhost:5432/gamemetrix
```

Docker Compose builds the backend's `DATABASE_URL` from the separate,
non-superuser `APP_DB_USER` and `APP_DB_PASSWORD` values:

```text
postgresql+psycopg://<APP_DB_USER>:<APP_DB_PASSWORD>@db:5432/<POSTGRES_DB>
```

Compose therefore overrides any host-only `DATABASE_URL` from `backend/.env`;
provider credentials still come from that file. `ENV`, `APP_DB_USER`, and
`APP_DB_PASSWORD` are mandatory. The PostgreSQL bootstrap/admin credential is
never passed to the backend container.

`DATABASE_URL` is required. The backend intentionally supports one runtime
database: PostgreSQL.

To merge an existing `backend/gamemetrix.dev.db` catalog into an empty or
partially populated PostgreSQL database, preview the operation first and then
apply it:

```powershell
cd backend
python scripts\migrate_legacy_sqlite.py
python scripts\migrate_legacy_sqlite.py --apply
```

The source SQLite file is opened read-only. Existing PostgreSQL games win on
slug; legacy-only games and related snapshot rows are copied with remapped IDs.

PostgreSQL is the only runtime source of truth in development, tests, Docker,
and production. The ignored `backend/gamemetrix.dev.db` file is a legacy
read-only migration/archive input, not a fallback database. Keep it only until
the PostgreSQL dump and migrated row counts have been verified; the application
deliberately rejects a SQLite `DATABASE_URL` instead of silently creating a
second catalog.

Copy the non-secret settings from `backend/.env.example` and fill the provider
credentials you use. API Health reports rejected, expired, and misrouted
providers without returning credential values.

The full 50k-row classify/rescore/deduplicate pass is intentionally disabled on
ordinary boots (`STARTUP_CATALOG_MAINTENANCE_ENABLED=false`) so API readiness
does not wait behind a CPU- and memory-heavy maintenance scan. Enable it for one
controlled restart only when that complete recomputation is explicitly needed.

The Compose PostgreSQL service is deliberately tuned below its 160 MiB cgroup
limit (`shared_buffers=64MB`, `work_mem=2MB`,
`maintenance_work_mem=32MB`, `max_connections=40`). Keep those values aligned
with the container memory limit if deployment resources change.

Visitor counts are available in the admin dashboard. To retain exact IPs for
new visits, set `ANALYTICS_STORE_RAW_IP=true`; raw IPs are removed after
`ANALYTICS_RAW_IP_RETENTION_DAYS` while their hashes remain usable for unique
counts. Behind the bundled nginx proxy, also set
`ANALYTICS_TRUST_PROXY_HEADERS=true`. Do not enable trusted proxy headers when
the backend is directly reachable from the internet.

Analytics collection starts only after the visitor explicitly allows it in the
site privacy control. Browser IDs are pseudonymous browser-storage identifiers,
network IDs are hashed IP addresses, and neither is an exact person count.
Automated user agents and browsers marked as internal traffic are excluded from
newly collected metrics. Set `VITE_GA_MEASUREMENT_ID=G-...` in the root
deployment environment to add consented GA4 collection; ad storage, Google
signals, and advertising personalization remain disabled.

## Run Backend

```powershell
python -m pip install -r backend\requirements-dev.txt
cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`.

Run one recorded, resumable data-fill cycle without starting the web server:

```powershell
python scripts\run_data_fill_once.py --target-total 50000
```

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

The SSR app runs at `http://127.0.0.1:5173`. Server loaders use
`INTERNAL_API_BASE_URL` when set and otherwise call `http://127.0.0.1:8000`.
Browser API calls stay same-origin; the development server proxies `/api` and
backend `/admin/*` requests to port 8000 so account cookies behave like production.

## Accounts

Normal accounts and admin authentication are intentionally separate. Normal
accounts use Argon2id passwords and hashed opaque sessions in PostgreSQL;
admin continues to use `/api/auth/token` and a short-lived Bearer token. The
admin token is held in page memory only and is never written to browser storage.

Development can use `ACCOUNT_EMAIL_DELIVERY=log`. Production requires
`ENV=production` and validates HTTPS, JWT issuer/audience, SMTP, numeric job
limits, and admin settings before startup. Configure Google OAuth and SMTP only
in backend/deployment secrets.

## Verify

```powershell
cd backend
python -m pytest -q
python -m compileall app alembic

cd ..\frontend
npm run lint
npm run typecheck
npm run build
npm run test:e2e
npm run lighthouse:ci

cd ..
docker compose config
```

PostgreSQL integration tests run when `TEST_DATABASE_URL` names a dedicated
database ending in `_test`.

Operational policy is documented in [SEO growth](docs/seo-growth.md) and
[provider access](docs/provider-access.md). The ordered production hardening
and rollback procedure is in
[Production security rollout](docs/production-security-runbook.md).
