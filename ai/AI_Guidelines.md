# GameMetrix — AI Development Guidelines

Rules every AI session on this project must follow without exception. Read this before writing a single line of code.

---

## 0. Before Starting Any Task

1. Read `memory/MEMORY.md` and follow all linked memory files relevant to the task.
2. Read this file entirely.
3. If the task touches scoring, read `backend/app/integrations/sync.py` and `source_registry.py` before touching anything.
4. If the task touches the frontend, read `frontend/src/types/game.ts` before adding or renaming fields.
5. Do NOT infer the current state of the codebase from memory alone — memory can be stale. Always verify by reading the actual file.

---

## 1. Core Invariants (Never Violate)

| # | Rule |
|---|------|
| **I-1** | `value_score` is NEVER an input to `calculate_metrix_score()`. It is a separate, parallel signal. |
| **I-2** | Awards (`award_count`, `goty_year`) are NEVER added as a score bump to `metrix_score`. They are display-only badges. |
| **I-3** | Raw API responses are NEVER written directly to the database. Every source must produce a `NormalizedGame` or `ExternalScore` first. |
| **I-4** | Source names (`"Metacritic"`, `"Steam"`, etc.) are NEVER hardcoded in multiple places. `source_registry.py` is the single source of truth for source metadata. |
| **I-5** | `PRIOR_VOTE_COUNTS` in `sync.py` and `prior_count` in `source_registry.py` must always stay in sync. If you change one, change the other in the same commit. |
| **I-6** | The sidebar stays short — no per-year entries. "Best of the Year" is one sidebar item; year selection happens via in-page chips. |
| **I-7** | `applicable_for_game()` in `source_registry.py` is the authoritative function for which sources apply to a game. The `Game.applicable_primary_sources` property delegates to it — never re-implement this logic inline. |

---

## 2. Architecture — Backend Layer Map

```
main.py
  └─ App bootstrap only: CORS, lifespan, router mounting, /health.
     No business logic. No direct integration imports.

routers/
  ├─ games.py    — public game endpoints (search, list, detail, refresh, trailer, facets)
  ├─ imports.py  — bulk import endpoints (rawg, steamspy, cheapshark, free-to-game)
  ├─ ratings.py  — rating/metadata maintenance (weights, enrich, fix-years, enrich-summaries)
  └─ admin.py    — internal debug endpoints (health checks, price import, external-id matching)

services/
  ├─ metadata.py      — summary cleaning, enrichment, release-year fixing
  ├─ rawg_import.py   — RAWG search result → Game creation and metadata application
  ├─ game_filter.py   — list filtering, deduplication, in-memory sorting
  ├─ game_query.py    — catalog SELECT/COUNT construction (CatalogFilters, sorts, JSON-array predicates)
  ├─ trailer_cache.py — TTL + in-flight coalescing for YouTube trailer lookups
  └─ background.py    — periodic refresh loops (daily_refresh_loop, fix_year_batch, refresh_rating_batch)

integrations/
  ├─ sync.py            — Bayesian scoring (calculate_metrix_score) + refresh orchestration
  ├─ source_registry.py — canonical source definitions (weight, prior_count, requires_pc, etc.)
  ├─ types.py           — shared dataclasses: ExternalScore, NormalizedGame, SourceHealth
  └─ <source>.py / <source>_service.py — one pair per data source (thin HTTP client + normalizer)

models.py   — ORM models only. Properties must use source_registry imports; no duplicated sets.
schemas.py  — Pydantic API schemas only.
config.py   — All os.getenv calls live here. No other file may call os.getenv.
database.py — SQLAlchemy engine and session factory only.
```

### Dependency rule (call downward only):
```
main → routers → services → integrations/sync → integrations/<source>
                           → models
                           → integrations/source_registry
```
No upward calls. `sync.py` may call `services/metadata.py` for enrichment (one permitted cross-call; avoids a circular dependency). `models.py` imports from `integrations/source_registry.py` only.

---

## 3. Single-Function Rule

Every function must do exactly ONE thing:
- `calculate_metrix_score` — computes the score, nothing else.
- `_bayesian_adjust` — computes adjusted score + reliability, nothing else.
- `_confidence` — computes confidence from scoring context, nothing else.
- `dedupe_near_duplicates` — deduplicates a list, nothing else.
- Each `filter_by_*` function — one filter condition, nothing else.
- `clean_game_summary` — sanitizes text, nothing else.
- `summary_needs_enrichment` — returns bool, nothing else.
- `enrich_game_summary` — async fetch + mutate, nothing else.
- `fix_game_year` — year fixing only, nothing else.
- `game_from_rawg_search` — creates a new Game from RAWG data, nothing else.
- `apply_rawg_to_game` — updates an existing Game from a RAWG search hit, nothing else.
- `apply_rawg_metadata` — applies full detail metadata, returns bool if changed.

If a function needs a docstring to explain what ELSE it does, split it.

---

## 4. Adding a New Data Source

Follow this checklist in order — do not skip steps:

1. Add a `SourceDef` entry to `source_registry.py` with correct `weight`, `is_primary`, `requires_pc`, `prior_count`, and `display_priority`.
2. Add the same `prior_count` value to `PRIOR_VOTE_COUNTS` in `sync.py` and the same `weight` to `SOURCE_WEIGHTS`.
3. Create `integrations/<source>.py` — thin HTTP client, returns raw dict.
4. Create `integrations/<source>_service.py` — converts raw dict to `NormalizedGame` / `ExternalScore`.
5. Register in `refresh_game_sources()` in `sync.py`, guarded by `game.is_pc_applicable` if `requires_pc=True`.
6. Add a health-check entry to `provider_status.py`.
7. Update `frontend/src/types/game.ts` if new fields are exposed in the API response.
8. If the source is non-rating (price, popularity), `weight=0.0` and it must never enter `calculate_metrix_score()`.

---

## 5. Scoring Algorithm Rules

- Bayesian formula: `adjusted = (70 * prior_count + raw * review_count) / (prior_count + review_count)`
- Confidence formula: `min(1.0, 0.15 + 0.35*coverage + 0.50*evidence)` — evidence outweighs coverage.
- `_bayesian_adjust` and `_confidence` are separate functions — keep them that way.
- `confidence_level` tiers: `Strong`, `Solid`, `Limited`, `Catalog`. Defined in `models.py`. Do not add tiers without user approval.
- Source weights must sum to ~1.0 across primary sources. Verify after any weight change.
- When changing the algorithm, test against: Elden Ring, Stardew Valley, a console-only game, a low-review indie.

---

## 6. Services Layer Rules

- `services/metadata.py` owns all text cleaning and enrichment. Never duplicate `_WEAK_SUMMARY_MARKERS`.
- `services/game_filter.py` owns deduplication and all `filter_by_*` functions. Add new filter conditions here.
- `services/rawg_import.py` owns all RAWG → Game conversion logic. Route handlers must not build `Game` objects directly from RAWG API dicts.
- `services/background.py` owns the periodic refresh loop. Timing constants come from `config.py` via `get_settings()`.

---

## 7. Frontend Rules

- `types/game.ts` is the canonical type for API-facing game data. Update before updating components.
- `services/games.ts` is the only file that calls the backend API. Components never `fetch()` directly.
- `catalog/` owns catalog-shell concerns, not UI: `config.ts` (page types, `DEFAULT_FILTERS`, nav items, presets, sort options, page copy), `snapshot.ts` (sessionStorage back-nav restore), `useCatalogScroll.ts` (masthead auto-hide + scroll-to-top). Nav entries and preset copy go in `config.ts` — never inline in `App.tsx`.
- `App.tsx` is the catalog container: state, data fetching, and snapshot restore only. Markup belongs in `components/`.
- `state/collections.ts` and `CollectionsProvider` own all user-collection state.
- **TypeScript strict mode** is on. Never use `any`; use `unknown` and narrow. Avoid `as` casts.
- **Icons:** Lucide only (`lucide-react`). No other icon libraries.
- **CSS:** scoped `.css` files or `App.css`. No inline `style={{}}` for non-dynamic values.
- **Compact grid is the DEFAULT view.** Any new card layout must preserve both `list` and `compact` modes.
- **Score ring colors:** green = Strong, lime = Solid, amber = Limited. Do not change without updating both sides.

---

## 8. API & Database Rules

- New endpoints go in the appropriate `routers/` file. Register via `app.include_router()` in `main.py`.
- All query params must be validated in the route signature via Pydantic/FastAPI types — no `request.query_params` manual parsing.
- New DB columns must have a `default` or `server_default` so existing rows are not broken.
- If you add a column to `models.py` that should be API-exposed, also add it to `schemas.py`.
- Also add it to `_run_migrations()` in `main.py` with `_add_column_if_missing`.
- No `nullable=False` columns without a default unless you also back-fill existing rows.

---

## 9. Code Style Rules

- **No comments** unless the WHY is non-obvious.
- **No magic numbers** inline — use named constants at module level.
- **No duplicate logic** — if two files need the same transformation, it belongs in `services/` or `types.py`.
- **No feature flags or backward-compat shims** — delete old code; git history is the backup.
- **No `os.getenv` outside `config.py`** — always use `get_settings()`.
- Function signatures: prefer explicit typed parameters over `**kwargs`.
- Keep `sync.py` functions focused: `calculate_metrix_score` only scores; `refresh_game_sources` only orchestrates.

---

## 10. What Requires User Approval Before Implementing

- Any change to score weights, prior counts, or the confidence formula.
- Adding a new sidebar navigation item.
- Adding awards as any form of numeric score input.
- Changing `CollectionKey` enum values (breaks localStorage data for existing users).
- Introducing a new external API dependency.
- Any database schema change that drops or renames existing columns.
- Changing the default view mode away from compact grid.

---

## 11. Code Quality Rules

### Magic numbers and hardcoded config
- HTTP timeouts are module-level constants (`_HTTP_TIMEOUT = 12`), never literals inside function bodies.
- Threshold values (string length limits, score floors, year tolerances) are named constants at module top.
- URL strings are module-level constants (`_RAWG_GAMES_URL = "..."`), never embedded in function calls.
- All environment variables are read **only in `config.py`** via `get_settings()`. No `os.getenv` anywhere else.

### Error handling
- Never use bare `except Exception: pass`. At minimum log with `log.debug(…, exc_info=True)`.
- Use `log.exception(…)` for unexpected errors in background loops (includes traceback automatically).
- Expected failures (no API key, no matching game) return typed `ExternalScore(status="unavailable")`, not exceptions.
- HTTP errors: check `response.is_success` and return a typed unavailable response, not a crash.

### Type hints
- Every public function has full parameter and return type annotations.
- Every private helper (`_build_*`, `_extract_*`, `_parse_*`) also has full annotations.
- Use `dict[str, str]`, `list[Game]`, `tuple[float | None, float | None]` — not bare `dict`, `list`, `tuple`.
- Do NOT use `Any`. Use `Unknown` and narrow, or use precise union types.

### Single responsibility
- Each function does exactly one thing. If a docstring needs to say "and also", split the function.
- Integration files (`igdb.py`, `steam.py`, etc.): HTTP client + response parsing only.
- Service files (`metadata.py`, `rawg_import.py`, etc.): business transformations only. No HTTP calls (use integration functions).
- Router handlers: orchestrate service calls and return HTTP responses. No business logic inline.

### Security-sensitive logic
- API keys are never logged, never included in error responses, never passed as query params in log output.
- `config.py` exposes `is_*_configured()` bool methods — callers check availability without touching raw key values.
- The `_build_headers()` pattern in `opencritic.py` is the standard for auth header construction: build once, pass to client.

### Dependencies
- Do not add new third-party packages without explicit user approval.
- Prefer Python stdlib over third-party for simple tasks (use `re`, `html`, `urllib.parse` before adding new libs).

---

## 12. Task Completion Checklist

Before reporting a task as done:

- [ ] `source_registry.py` `prior_count` and `weight` are in sync with `sync.py` `PRIOR_VOTE_COUNTS` and `SOURCE_WEIGHTS` if touched.
- [ ] `frontend/src/types/game.ts` matches any new API response fields.
- [ ] No `any` types introduced in TypeScript.
- [ ] No hardcoded source name strings outside `source_registry.py`.
- [ ] `value_score` is not wired into `metrix_score` if price logic was touched.
- [ ] New DB columns have defaults and are added to `_run_migrations()` in `main.py`.
- [ ] New service functions do exactly one thing (no mixed concerns).
- [ ] No `os.getenv` calls outside `config.py`.
- [ ] No magic number literals in function bodies — all are named constants.
- [ ] No bare `except Exception: pass` — errors are logged.
- [ ] All new functions have full type annotations.
- [ ] If UI changed: both `list` and `compact` view modes still work.
