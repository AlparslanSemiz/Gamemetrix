# GameMetrix — System Map for AI Agents

**Purpose:** this file replaces "read the whole codebase first". Any AI agent (Claude Code,
Cursor, Copilot, Codex, …) should be able to read this file plus `ai/AI_Guidelines.md` and then
go straight to the 2–5 files a task actually touches.

**Read order for a new session**

1. `AI.md` (this file) — what the system is and where things live.
2. `ai/AI_Guidelines.md` — the rules you must not break (invariants, style, approval gates).
3. Only the specific files your task touches.

**This file describes structure and data flow. It does not repeat the rules.**
Invariants, code style, approval gates and the task checklist live in `ai/AI_Guidelines.md`.

**Do not trust this file over the code.** It is maintained by hand and can drift. Verify any
line you are about to depend on by reading the actual file. If you find drift, fix this file
in the same change (see [Doc maintenance](#14-doc-maintenance)).

---

## 1. The product in one paragraph

GameMetrix is a game decision catalog: it aggregates ratings from several external sources into
one reliability-weighted **GameMetrix Score**, enriches each game with metadata (playtime, price,
system requirements, Linux/Proton compatibility, screenshots, DLC), and lets a visitor filter,
rank and save games into personal collections. Roughly 50k games. The differentiator is that a
95 backed by one source does not rank like a 95 backed by four — coverage, critic/user balance
and review volume shrink a thin score toward a neutral baseline.

---

## 2. Stack and runtime topology

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.x ORM, Alembic migrations |
| Database | PostgreSQL — **the only supported runtime DB**; a SQLite `DATABASE_URL` is rejected |
| Frontend | React Router **Framework Mode** (SSR), React + TypeScript strict, Vite |
| Proxy | nginx (`nginx.conf`) in front of both, Cloudflare in front of that |
| Deploy | `docker-compose.yml` — services: `db`, `backend`, `frontend`, `nginx`; volume `pgdata` |
| Host constraint | 1 GB RAM production host. This drives several designs — see §9. |

Ports in development: backend `127.0.0.1:8000`, SSR frontend `127.0.0.1:5173`. The Vite dev
server proxies `/api` and `/admin/*` to 8000 so account cookies behave like production.

Server-side loaders call the backend through `INTERNAL_API_BASE_URL`
(`frontend/src/server-api.server.ts`); browser calls stay same-origin.

---

## 3. Repository map

```
backend/            FastAPI app, Alembic migrations, tests, one-off scripts
frontend/           React Router SSR app
ai/                 AI_Guidelines.md (rules), CHECKSTYLE-light.md
docs/               seo-growth.md, provider-access.md, production-security-runbook.md
ops/                deploy + server hardening shell scripts, nginx TLS variants, locustfile
memory_bank/        older narrative project notes (historical; AI.md supersedes for architecture)
reports/            generated analysis output
nginx.conf          production proxy config
docker-compose.yml  full stack; docker-compose.production.yml layers prod overrides
update_proton.py    root-level ProtonDB helper
```

---

## 4. Backend layer map

```
main.py
  App bootstrap only: settings validation, CORS, rate limiting, cache-control
  and admin-audit middleware, router mounting, /health, and the lifespan that
  seeds the DB and starts the background loops. No business logic.

routers/            HTTP surface. Orchestrate services, return schemas. No business logic.
  games/            search · catalog · catalog_summary · detail · admin_actions
  account/          auth · oauth · state · preferences · alerts · schemas
  admin/            health · dashboard · jobs · diagnostics · matching · prices · sources
  imports.py        bulk catalog imports (admin, heavy-job gated)
  ratings.py        score weights, enrich, fix-years, refresh-all, rate limits
  analytics.py      consented page-view / event ingestion
  auth.py           admin JWT token endpoint
  seo.py            sitemaps, genre pages, curated collections

services/           Business transformations. No direct HTTP to providers.
  background.py             the periodic loops (rating refresh, metadata, HLTB, summary, endless, retention)
  data_fill/                orchestrator · stages · runs · status — the ordered full-catalog fill
  metadata.py               summary cleaning, enrichment, release-year fixing
  metadata_backfill/        sanitize → gaps → persistence → apply → sources → batch
  summarizer/               AI-audited descriptions: text · issues · ai · batch
  catalog_quality/          AI review of suspicious rows: signals · review · research · remediation · batch · repair_batch
  similarity/               "games like X": taxonomy → signals → profiles → scoring/gates → ranking → queries (+ cache, ai_rerank)
  deduplication/            titles → matching → merge → in_memory → store
  game_query.py             catalog SELECT/COUNT construction (CatalogFilters, sorts, JSON predicates)
  game_filter.py            in-memory list filtering and sorting
  catalog_projection.py     ORM row → list/card payload
  seo.py / completeness.py  indexability state, data-completeness scoring
  endless.py                "no fixed completion time" classification
  *_backfill.py             one-purpose sweeps (price, HLTB, IGDB scores/playtime/optional metadata,
                            metacritic, primary scores, steam system requirements)
  account_*.py, google_identity.py, notification_digest.py   account-side concerns
  admin_audit.py, admin_dashboard.py, api_sources.py, job_heartbeat.py   ops surfaces

integrations/       Thin provider clients + normalizers. HTTP and parsing only.
  source_registry.py    canonical source definitions — the single source of truth for source metadata
  types.py              shared dataclasses: ExternalScore, NormalizedGame, SourceHealth
  sync/                 the scoring engine (see §6)
  rawg/ steam/ hltb/    multi-file provider packages
  <source>.py           thin HTTP client returning raw dicts
  <source>_service.py   raw dict → NormalizedGame / ExternalScore
  ai.py, ai_types.py    provider-agnostic text generation with an ordered fallback chain
  groq.py, gemini.py, cloudflare_ai.py, openrouter.py   the AI providers behind that chain
  rate_limiter.py       DB-backed per-source daily/window request and token budgets
  provider_status.py    health checks surfaced in the admin API Health panel

models/             ORM tables only, grouped by domain (see §5).
game_signals.py     Pure rating-signal classification. Leaf module — importable from anywhere.
content_type.py     Classifies a row as game / dlc / soundtrack / demo / mod / utility / software.
                    Leaf module. `non-game` is set ONLY by the AI-confirmed cleanup and is never
                    re-inferred — inference is exactly what missed it (see main.py).
schemas.py          Pydantic API schemas only.
config.py           Every os.getenv call lives here. No other file may read the environment.
config_validation.py Settings validation; reads no environment itself.
database.py         Engine + session factory only.
security.py         Admin JWT (require_admin_user).
account_security.py Normal-account auth (Argon2id passwords, hashed opaque sessions).
rate_limit.py       slowapi HTTP rate limiting (distinct from integrations/rate_limiter.py).
heavy_jobs.py       HEAVY_JOB_LOCK + peak-hour gate shared by all bulk jobs.
```

### Dependency rule — call downward only

```
main → routers → services → integrations/sync → integrations/<source>
                          → models → game_signals → integrations/source_registry
                          → content_type
```

Two long-standing upward exceptions, both intentional, both documented in the code:

- `integrations/sync/refresh.py` imports `services/metadata|seo|completeness` lazily inside the
  function to avoid an import cycle.
- `integrations/rawg/` reaches up into `services/rawg_import` and `services/deduplication`.

Do not add new upward calls.

### Module splitting convention

When a module passes ~400 lines or holds two unrelated concerns, split it into a package with one
module per responsibility and re-export the public API from `__init__.py`, so existing import
paths keep working. `models/`, `routers/games/`, `services/similarity/` and the rest all followed
this path — that is why `from ..models import Game` still works.

---

## 5. Data model

`backend/app/models/` — four domain modules, all re-exported from `__init__.py`.

| Module | Tables |
|---|---|
| `catalog.py` | `Game`, `ExternalId`, `RatingSnapshot`, `SourceSnapshot`, `PriceSnapshot` |
| `accounts.py` | `User`, `AccountSession`, `AccountToken`, `OAuthIdentity`, `UserCollection`, `UserPreference`, `UserAlertState`, `NotificationDelivery` |
| `analytics.py` | `VisitEvent`, `AnalyticsEvent` |
| `ops.py` | `ApiRequestBudget`, `ApiRequestWindow`, `AdminAuditLog`, `AiCatalogChange`, `CatalogQualityReview`, `CatalogSyncState`, `DataFillRun`, `JobRun` |

### `Game` — the central row

Stored columns worth knowing:

- **Identity/content:** `title`, `slug`, `summary`, `summary_short`, `cover_url`, `screenshots`,
  `content_type`, `franchise`, `developer`, `publisher`, `genres`, `platforms`, `game_modes`.
- **Scores:** `source_scores` (JSON list — one row per source, the input to scoring),
  `metrix_score`, `rank_score`, `is_rankable`, `critic_score`, `user_score`, `metacritic_score`.
- **Enrichment:** `playtime_minutes`, `hltb_*`, `is_endless`, `proton_tier`, `proton_score`,
  `system_requirements`, `dlcs`, `similar_games`, `steam_app_id`, `website_url`.
- **Awards (display only):** `award_count`, `award_nominations`, `goty_year`, `awards`.
- **Freshness bookkeeping:** `ratings_refreshed_at`, `metadata_refreshed_at`, `prices_refreshed_at`,
  `hltb_refreshed_at`, `summary_refreshed_at`, `summary_checked_at`, `summary_quality`,
  `endless_checked_at`, `data_complete`, `catalog_added_at`.
- **SEO:** `seo_indexable`, `seo_exclusion_reason`, `seo_updated_at`.

Computed properties on `Game` delegate to `game_signals.py` — never re-implement them inline:
`is_pc_applicable`, `applicable_primary_sources`, `applicable_sources`, `applicable_source_count`,
`live_primary_source_count`, `confidence_level`, `data_strength`, `rank_exclusion_reason`,
`score_profile`, `popularity_label`.

### Snapshots

`RatingSnapshot` is append-only; the latest row per `(game_id, source)` is authoritative.
`SourceSnapshot` is a raw-response audit log for debug/replay — **never** an input to scoring.
`PriceSnapshot` holds current + historical price per game/store.

### Migrations

**Alembic owns the schema.** `backend/alembic/versions/` — 17 revisions as of 2026-07-29,
baseline `20260720_0001_postgres_baseline`. Run `alembic upgrade head`.

> There is no `_run_migrations()` / `_add_column_if_missing()` in `main.py` any more. Older notes
> that tell you to add columns there are stale — write an Alembic revision instead.

---

## 6. The scoring pipeline — core domain logic

This is the part of the system worth understanding before changing anything near it.

### Source taxonomy — `integrations/source_registry.py`

| Source | Type | Weight | Primary | PC-only |
|---|---|---|---|---|
| Metacritic | critic | 0.32 | yes | no |
| OpenCritic | critic | 0.28 | yes | no |
| Steam | user | 0.25 | yes | **yes** |
| IGDB | user | 0.15 | yes | no |
| RAWG | aggregate | 0.00 | no | no |
| SteamSpy | popularity | 0.00 | no | yes |
| CheapShark, ITAD | price | 0.00 | no | yes |
| FreeToGame | metadata | 0.00 | no | no |

Weight `0.0` structurally guarantees a source can never enter the score. `SOURCE_WEIGHTS` in
`sync/constants.py` is **derived** from this registry — change the registry, never the constant.

`applicable_for_game(platforms)` is the authoritative answer to "which sources apply to this
game". A console-only game has 3 applicable sources, a PC game has 4 — so a Switch exclusive is
never penalized for missing Steam data, and `refresh_game_sources` skips the Steam call entirely.

### The score — `integrations/sync/scoring.py`

A **reliability-adjusted weighted average**, not Bayesian prior shrinkage. An earlier Bayesian
`prior_count` model was removed; do not reintroduce its vocabulary.

```
raw       = weighted average of the live primary scores
adjusted  = raw * reliability  +  70 * (1 - reliability)  -  (1 - reliability) * 6
```

`reliability = clamp(coverage + balance + volume, 0.46, max_for_coverage)`:

- **coverage** by live primary count — `0 → 0.40, 1 → 0.62, 2 → 0.78, 3 → 0.90, 4 → 1.00`,
  each with its own reliability ceiling (`0.46 / 0.68 / 0.84 / 0.94 / 1.00`).
- **balance** — critic *and* user `+0.03`, critic only `−0.04`, user only `−0.06`, neither `−0.10`.
- **volume** by total review count — `≥100k +0.04`, `≥10k +0.02`, `≥500 +0.01`, `0 −0.04`, else `−0.02`.

Every one of these is a named module-level constant and a **published-score input**. Admin weights
(`/api/score-weights`) provide the editorial baseline; `SCORE_WEIGHT_<SOURCE>` env values act as
relative deployment-level multipliers on top.

`calculate_metrix_score` scores and nothing else. `_score_reliability_factor` computes the
multiplier and nothing else. Keep them separate.

### Confidence tiers — `game_signals.py`

`Strong` / `Solid` / `Limited` / `Catalog`, derived from live source count and review volume
(`STRONG_MIN_SOURCES=3`, `STRONG_MIN_REVIEWS=500`, `SOLID_MIN_SOURCES=2`, …). Drives the score
ring color (green / lime / amber) and `rank_exclusion_reason`.

### Refresh flow — `integrations/sync/`

```
refresh.py   orchestrates one game end-to-end
  ├─ cache.py         game_needs_rating_refresh? cached_score reuse
  ├─ fetching.py      per-source fetch plan, budget-gated, PC-gated
  ├─ serialization.py ExternalScore ↔ stored row, merge_source_scores
  ├─ scoring.py       calculate_metrix_score
  ├─ ranking.py       compute_rank_fields → rank_score, is_rankable
  └─ persistence.py   RatingSnapshot / SourceSnapshot / ExternalId writes
```

**Raw API responses are never written to `Game` directly** — every source produces a
`NormalizedGame` or `ExternalScore` first (`integrations/types.py`).

### Separate, parallel signals — never score inputs

- `value_score` (`integrations/value_score.py`) — 40 pts quality + 30 pts deal quality vs.
  historical low + 20 pts $/hour + 10 pts active-sale bonus. Its own number, shown alongside.
- Awards / GOTY — display-only badges.
- ProtonDB tier — Linux/Steam Deck compatibility display only, not in `source_registry`.
- SteamSpy ownership — popularity label only.

---

## 7. Background jobs

Started in `main.py`'s lifespan, defined in `services/background.py` (plus `data_fill/` and
`notification_digest.py`). Each is an infinite loop with a staggered startup delay so they do not
all wake at once on a 1 GB host. Every cycle is wrapped in `record_job_run(...)`, which is what
the admin **`GET /admin/jobs/periodic`** panel reads out of the `job_runs` table.

| Loop | Startup delay | Cadence (setting) | Does |
|---|---|---|---|
| `daily_refresh_loop` | 30 s | `REFRESH_ALL_INTERVAL_HOURS` (6) | `refresh_all_games` + `fix_year_batch` |
| `metadata_backfill_loop` | 45 s | `METADATA_BACKFILL_INTERVAL_MINUTES` (30) | covers, summaries, dev/publisher, screenshots, requirements, external IDs |
| `hltb_backfill_loop` | 90 s | `HLTB_BACKFILL_INTERVAL_MINUTES` (60) | HowLongToBeat playtimes (scraped — deliberately slow) |
| `summary_audit_loop` | 120 s | `SUMMARY_SHORTEN_INTERVAL_MINUTES` | rotates the catalog auditing/rewriting descriptions, derives `summary_short` |
| `endless_backfill_loop` | 150 s | `ENDLESS_BACKFILL_INTERVAL_MINUTES` | flags roguelikes/MMOs/sandbox as `is_endless` (∞ instead of "missing playtime") |
| `data_fill_loop` | — | `DATA_FILL_*` | the ordered full-catalog fill, see below |
| `notification_digest_loop` | — | — | account alert digests |
| `raw_analytics_retention_loop` | 120 s | 6 h | redacts raw IP/user-agent past the retention window |

`_background_startup` runs the expensive full-catalog classify/rescore/dedupe pass **only** when
`STARTUP_CATALOG_MAINTENANCE_ENABLED=true`. It is off by default so API readiness is not blocked
behind a 50k-row scan.

### Data fill — `services/data_fill/`

One recorded, resumable run executes stages in this order (`orchestrator.py`):

```
catalog → metacritic → igdb_scores → hltb → igdb_playtime → igdb_optional_metadata
→ system_requirements → primary_scores → ratings → metadata → endless → summaries → prices
```

Order is deliberate: free/cheap sources seed the expensive slots first (e.g. Metacritic is seeded
from free CheapShark data before RAWG budget is spent). Runs are recorded in `data_fill_runs`,
interrupted runs are closed on boot by `recover_interrupted_runs()`, and status is exposed at
`GET /admin/data-fill/status`.

---

## 8. Quotas, budgets and heavy-job safety

Three independent mechanisms — do not confuse them.

1. **`rate_limit.py`** — slowapi HTTP rate limiting on *inbound* requests
   (`PUBLIC_READ_RATE_LIMIT`, `AUTH_RATE_LIMIT`).
2. **`integrations/rate_limiter.py`** — DB-backed *outbound* provider budgets in
   `api_request_budgets` / `api_request_windows`: per-source daily request limits, daily **token**
   limits for AI providers, sub-day windows (e.g. `ITAD_FIVE_MINUTE_LIMIT`,
   `OPENCRITIC_PER_SECOND_LIMIT`), temporary blocks after a 429, and budget sharing between
   aliases. `acquire(source, estimated_tokens)` before a call; `settle_tokens` after.
   Limits come from `Settings`, so every process shares the same numbers.
3. **`heavy_jobs.py`** — `HEAVY_JOB_LOCK`, one shared `asyncio.Lock` across *all* bulk jobs.
   Imports and `refresh_all_games` acquire the **same** lock, so two of them can never run
   concurrently and an overlapping trigger fails fast with 429 instead of OOM-killing the host.
   `require_not_peak_hours` additionally rejects heavy jobs during a configured traffic window.

Default daily limits (`config.py`): OpenCritic 190, RAWG 600/day + 20 000/month, IGDB 20 000,
Steam 10 000, SteamSpy 300, CheapShark 200, FreeToGame 200, ITAD 200, HLTB 250, Wikidata 200.

### AI text generation — `integrations/ai.py`

Provider-agnostic with an **ordered fallback chain**, `AI_PROVIDER_ORDER=groq,gemini,cloudflare,openrouter`.
Groq is the default first hop (it is *Groq*, not "Grok"). `ai.py` owns retry policy, jitter,
in-flight deduplication, JSON-fence stripping, response validation, and token accounting against
the rate limiter. Providers raise a sanitized `ProviderFailure` with an `ErrorCategory` — raw
response bodies never cross that boundary. Failure categories that definitely did not consume
quota (rate-limited, auth, invalid model, not configured) do not charge the budget.

Consumers: `services/summarizer/`, `services/catalog_quality/`, `services/endless.py`,
`services/similarity/ai_rerank.py`. AI work is gated behind deterministic checks first — the AI
is only asked about rows the cheap heuristics could not settle.

---

## 9. Constraints that explain odd-looking code

The production host has **1 GB RAM**. Several designs exist only because of it:

- `db.expunge_all()` between the two full-catalog passes in `_seed_and_classify`, so one copy of
  the catalog is in memory instead of two.
- `yield_per` streaming + `load_only` + `noload` in `background._rating_refresh_plan` instead of
  materializing 50k `Game` objects.
- The single shared `HEAVY_JOB_LOCK`.
- `STARTUP_CATALOG_MAINTENANCE_ENABLED=false` by default.
- Compose PostgreSQL is tuned below its 160 MiB cgroup limit (`shared_buffers=64MB`,
  `work_mem=2MB`, `maintenance_work_mem=32MB`, `max_connections=40`). Keep these aligned with the
  container memory limit if deployment resources change.

---

## 10. Frontend architecture

### Routes — `frontend/src/routes.ts`

`/` · `/game/:slug` · `/best/games/:year` · `/best/:collection` · `/deals` · `/login` ·
`/register` · `/forgot-password` · `/reset-password` · `/verify-email` · `/unsubscribe` ·
`/account` · `/alerts` · `/settings` · `/about` · `/admin` · `*` (not-found)

Public game and curation routes render on the server; the catalog stays interactive after
hydration.

### Data flow

```
routes/*.tsx        loaders (server) → server-api.server.ts → backend
  └─ pages/*        page components
       └─ components/  presentation
services/games.ts   the ONLY file that calls the backend from the browser
services/api.ts     API_BASE_URL resolution
types/game.ts       canonical API-facing types — update this BEFORE components
```

### Catalog shell — `frontend/src/catalog/`

`App.tsx` is the catalog container: state, data fetching and snapshot restore only. Markup lives
in `components/`.

| File | Owns |
|---|---|
| `config.ts` | page types, `DEFAULT_FILTERS`, nav items, presets, sort options, page copy, URL deep-link filters |
| `snapshot.ts` / `snapshotRestore.ts` / `useCatalogSnapshot.ts` | sessionStorage back-nav restore |
| `useCatalogScroll.ts` | masthead auto-hide + scroll-to-top |
| `catalogFetch.ts`, `useCatalogPagination.ts`, `useCatalogBootstrap.ts`, `useCatalogActions.ts` | fetching, paging, bootstrap, actions |
| `useCollectionGames.ts`, `useTrailer.ts` | collection pages, trailer modal |
| `presentation.ts` | view-model shaping |

Nav entries and preset copy go in `config.ts` — never inline in `App.tsx`.

`PAGE_SIZE = 24`. Default sort is `rank_score` desc. `SIDEBAR_GROUPS` currently holds one group
("Deals": Best Deals, Free Games); collection pages come from `collectionNavItems`.

### Component structure

- `components/catalog-workspace/` — masthead, heading, results, utility panel.
- `components/game-card/` — `ListGameCard`, `CompactGameCard`, actions, source scores, badges,
  plus `model.ts` / `types.ts`. **Both `list` and `compact` modes must keep working.**
- `pages/detail/` — header, score summary, ratings panel, info table, gallery, DLC, price,
  system requirements, similar games, collection actions.
- `pages/admin/panels/` — one panel per admin surface, driven by `useAdminDashboard.ts`.

### State

- `state/collections.ts` + `CollectionsProvider` — all user-collection state.
  `CollectionKey` has **8 values**: `watchlist, playing, seen, completed, on_hold, dropped,
  liked, favorites`. localStorage key `gamemetrix.collections`, spread over `emptyCollections`
  on load for forward compatibility. Changing these keys breaks existing users' local data.
- `state/AccountProvider.tsx` + `state/account.ts` — signed-in account state; server-side
  collections sync through `/api/account/state`.

### Conventions

TypeScript strict, no `any` (use `unknown` and narrow, avoid `as`). Icons: `lucide-react` only.
CSS: scoped `.css` files or `App.css`, no inline `style={{}}` for non-dynamic values.
**Gotcha:** the `/game/:slug` route does not load `App.css` — colocate component CSS.

---

## 11. API surface

Public (`/api`):

```
GET  /api/games                      list + filter + sort          GET  /api/facets
POST /api/games/batch                                              GET  /api/catalog/games
POST /api/catalog/games/batch                                      GET  /api/games/{slug}
GET  /api/games/{slug}/similar       /series       /trailer
GET  /api/integrations/status        GET /api/score-weights
GET  /api/seo/genres                 GET /api/seo/curated/{collection}
GET  /sitemap.xml  /sitemap-games-{chunk}.xml  /sitemap-static.xml
POST /api/analytics/page-view  /api/analytics/event                GET /health
```

Accounts (`/api/account`, gated by `require_account_enabled`):

```
POST /register /email/verify /login /logout /password/forgot /password/reset
GET  /me /session /state /export      POST /state/merge
PUT|DELETE /collections/{collection_type}/{slug}
PATCH /preferences   POST /email/unsubscribe
GET  /oauth/google/start  /oauth/google/callback
PUT  /alert-state  /alert-state/{alert_key}
DELETE /api/account
```

Admin — `POST /api/auth/token` returns the admin JWT; everything below requires it:

```
/admin/*            dashboard, audit-logs, ai-changes, api-health, source-test/{source},
                    jobs/periodic, data-fill/status|run, primary-scores/status|run,
                    consolidate, catalog-quality (+ decision), external-ids/{id},
                    rating-snapshots/{id}, source-snapshots/{id}, match/external-ids,
                    import/prices/{itad,cheapshark}, api-sources
/api/import/*       rawg, rawg/nintendo, igdb/nintendo, igdb/full, steam/catalog, catalog,
                    free-to-game, cheapshark, steamspy, hltb, free-sources
/api/games/{slug}/  refresh-scores, fetch-screenshots, fetch-system-requirements, fetch-prices
/api/ratings/*      enrich, refresh-all      /api/score-weights (PUT, recalculate)
/api/metadata/*     fix-years, backfill, audit-descriptions, enrich-summaries
GET  /api/rate-limits    live provider budget status
```

Note `routers/ratings.py` has **no router-level admin dependency** — each route declares
`_admin=Depends(require_admin_user)` individually. Only `GET /api/integrations/status` and
`GET /api/score-weights` are public there; everything else in that module is admin. When adding a
route to `ratings.py`, add the dependency explicitly or it ships unauthenticated.

Admin auth is intentionally separate from normal accounts: admin uses a short-lived Bearer token
held in page memory only (never browser storage); accounts use Argon2id passwords and hashed
opaque sessions in PostgreSQL.

> `POST /api/auth/token` uses `OAuth2PasswordRequestForm` — the form fields **must** be named
> `username` and `password`. Renaming them to credential values has broken admin login twice.

---

## 12. Where do I change X?

| Task | Start here |
|---|---|
| Change a source weight | `integrations/source_registry.py` only — `SOURCE_WEIGHTS` derives from it |
| Change the score formula | `integrations/sync/scoring.py` (needs user approval) |
| Change confidence tiers | `game_signals.py` (needs user approval) |
| Add a new data source | `source_registry.py` → `integrations/<source>.py` → `<source>_service.py` → `sync/fetching.py` → `provider_status.py` → `types/game.ts` |
| Add a catalog filter | `services/game_query.py` (SQL) or `services/game_filter.py` (in-memory), then `types/game.ts` + `FilterBar.tsx` |
| Add an API field | `models/` → Alembic revision → `schemas.py` → `frontend/src/types/game.ts` |
| Add a DB column | Alembic revision in `backend/alembic/versions/` with a default or server_default |
| Add an endpoint | the right `routers/` module; packages auto-include their sub-routers |
| Add a periodic job | `services/background.py` + task in `main.py` lifespan + `record_job_run(...)` |
| Change a provider quota | `config.py` (`*_DAILY_LIMIT`) — never hardcode a limit at the call site |
| Change AI provider order | `AI_PROVIDER_ORDER` env; chain logic in `integrations/ai.py` |
| Add a nav item / preset | `frontend/src/catalog/config.ts` (sidebar additions need user approval) |
| Change card layout | `components/game-card/` — both `list` and `compact` must keep working |
| Change the detail page | `pages/detail/` + `pages/GameDetailPage.tsx` (remember: no `App.css` on this route) |
| Read any env var | `config.py` via `get_settings()`. Nowhere else. |

---

## 13. Verify

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

PostgreSQL integration tests run only when `TEST_DATABASE_URL` names a dedicated database ending
in `_test`. 42 backend test modules live in `backend/tests/`; `test_scoring.py`,
`test_sync_persistence.py` and `test_provider_budgets.py` are the ones most likely to catch a
regression in the core pipeline. Frontend e2e specs are in `frontend/tests/e2e/`.

Operational procedure lives in `docs/production-security-runbook.md`, `docs/provider-access.md`
and `docs/seo-growth.md`. Run and deployment commands are in `README.md`.

---

## 14. Doc maintenance

This file is only worth reading if it stays true. Update it **in the same change** that makes it
false — not later.

| If your change… | Update |
|---|---|
| adds/removes/renames a module, package or layer | §4 layer map |
| adds a table or a notable `Game` column | §5 |
| touches scoring, weights, tiers or the refresh flow | §6 (and `ai/AI_Guidelines.md` §1/§5) |
| adds, removes or re-times a background job | §7 |
| changes a quota, budget mechanism or the AI chain | §8 |
| adds a route, page, catalog hook or state key | §10 |
| adds, removes or renames an endpoint | §11 |
| changes where a common task starts | §12 |
| changes a build, test or verification command | §13, and `README.md` if user-facing |
| establishes a new rule or invariant | `ai/AI_Guidelines.md` — **not** here |

Then append one line to §15.

Keep the split clean: **AI.md describes what exists. AI_Guidelines.md dictates what you must do.**
A new rule never goes in AI.md; a new module never goes in AI_Guidelines.md.

---

## 15. Change log

One line per session that changed the architecture. Newest first. Skip purely cosmetic work.

- **2026-07-29** — `AI.md` created as the shared architecture map for all AI agents; `CLAUDE.md`
  added as the Claude Code entry point. `ai/AI_Guidelines.md` corrected for the `models/` and
  `routers/games/` package splits and for Alembic replacing `_run_migrations()`.
