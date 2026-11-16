<div align="center">

<img src="frontend/public/favicon.svg" alt="GameMetrix logo" width="80">

# GameMetrix

**A game decision catalog: ratings from several sources merged into one reliability-weighted score, for about 50k games.**

[![Python](https://img.shields.io/badge/backend-FastAPI-2b6cb0?style=flat)](backend/)
[![React Router](https://img.shields.io/badge/frontend-React%20Router%20SSR-2b6cb0?style=flat)](frontend/)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-2b6cb0?style=flat)](docs/running.md)

### [Open gamemetrix.me](https://gamemetrix.me)

</div>

## Why

A 95 backed by one source and a 95 backed by four sources and thousands of reviews are not the
same signal, but most catalogs rank them the same. GameMetrix aggregates ratings from several
external sources and shrinks thin scores toward a neutral baseline, based on source coverage,
critic/user balance and review volume. A visitor can then filter and rank games and save them
into personal collections.

## Features

- GameMetrix Score: one reliability-weighted score per game, built from several rating sources.
- Per-game metadata: playtime, price, system requirements, Linux/Proton compatibility, screenshots, DLC.
- Filter and sort the catalog; save games into personal collections.
- Public game and curation pages render on the server; the catalog stays interactive after hydration.
- Separate normal accounts (Argon2id, hashed opaque sessions) and admin authentication; admin dashboard with visitor counts.
- Analytics only after the visitor opts in; no counting of automated traffic.

## Status

Live at [gamemetrix.me](https://gamemetrix.me) and under active development. It runs on a
single small (1 GB RAM) host, which shapes several design choices; see [AI.md](AI.md).
Provider API access is limited by quotas ([docs/provider-access.md](docs/provider-access.md)).
No license file is included in this repository.

## Tech stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (the only supported runtime database)
- Frontend: React Router Framework Mode (SSR), React, TypeScript, Vite
- Deploy: Docker Compose with nginx in front, images built by GitHub Actions

## Run locally

PowerShell shown. On Linux and macOS the commands are the same, except that paths use `/` instead of `\` (for example `backend/requirements-dev.txt`).

```powershell
# 1. database (copy .env.example to .env first and set the passwords)
docker compose up -d db

# 2. backend, at http://127.0.0.1:8000 (needs backend/.env, see backend/.env.example)
python -m pip install -r backend\requirements-dev.txt
cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload

# 3. frontend, at http://127.0.0.1:5173 (in a second terminal)
cd frontend
npm install
npm run dev
```

Verification (`pytest`, `lint`, `typecheck`, `build`, `test:e2e`), the database and
provider configuration, analytics settings and the data scripts are in
[docs/running.md](docs/running.md).

## Project structure

```
backend/    FastAPI app, Alembic migrations, tests, one-off scripts
frontend/   React Router SSR app
ops/        production scripts: deploy, backup, watchdogs
docs/       running guide, provider access, SEO, security runbook
ai/         development rules (AI_Guidelines.md)
AI.md       architecture map: layers, data model, scoring, jobs, API
```

[CLAUDE.md](CLAUDE.md) is the entry point for Claude Code; [AI.md](AI.md) is the fastest
orientation for people too. Operational policy: [SEO growth](docs/seo-growth.md),
[production security rollout](docs/production-security-runbook.md).
