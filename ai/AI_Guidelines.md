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

These are non-negotiable. If a task seems to require violating one, stop and ask the user.

| # | Rule |
|---|------|
| **I-1** | `value_score` is NEVER an input to `calculate_metrix_score()`. It is a separate, parallel signal. |
| **I-2** | Awards (`award_count`, `goty_year`) are NEVER added as a score bump to `metrix_score`. They are display-only badges. |
| **I-3** | Raw API responses are NEVER written directly to the database. Every source must produce a `NormalizedGame` or `ExternalScore` first. |
| **I-4** | Source names (`"Metacritic"`, `"Steam"`, etc.) are NEVER hardcoded in multiple places. `source_registry.py` is the single source of truth. |
| **I-5** | `PRIOR_VOTE_COUNTS` in `sync.py` and `prior_count` in `source_registry.py` must always stay in sync. If you change one, change the other in the same commit. |
| **I-6** | The sidebar stays short — no per-year entries. "Best of the Year" is one sidebar item; year selection happens via in-page chips. |
| **I-7** | `applicable_for_game()` in `source_registry.py` is the authoritative function for determining which sources apply to a game. Never re-implement this logic inline. |

---

## 2. Architecture Rules

### Backend

- **Layering:** `main.py` → `routers/` → service files (`*_service.py`) → integration files (raw API clients). Each layer calls only the layer below it. `main.py` does NOT call integration files directly.
- **Service files** (`igdb_service.py`, `steam_service.py`, etc.) contain business logic and return `NormalizedGame` or `ExternalScore`. They never contain HTTP route definitions.
- **Integration files** (`igdb.py`, `steam.py`, etc.) are thin HTTP clients. They do API auth, request construction, and response parsing into Python dicts. No business logic lives here.
- **`sync.py`** owns the scoring algorithm, game refresh orchestration, and confidence calculation. Do not scatter scoring logic into service files.
- **`types.py`** owns shared dataclasses: `ExternalScore`, `NormalizedGame`, `SourceHealth`. Add new shared types here, not inline in modules.
- **`source_registry.py`** owns source metadata. Any new rating source requires a `SourceDef` entry before being referenced anywhere else.
- **`config.py`** owns all environment variable reads. Never call `os.environ` or `os.getenv` outside `config.py`.
- **`models.py`** owns ORM models. All DB writes go through SQLAlchemy ORM — no raw SQL `INSERT`/`UPDATE`.
- **`schemas.py`** owns Pydantic response schemas. API responses must be typed via schemas, never as raw dicts.

### Frontend

- **`types/game.ts`** is the canonical type for any game data crossing the API boundary. Update it before updating components.
- **`services/games.ts`** is the only file that calls the backend API. Components never `fetch()` directly.
- **`state/collections.ts`** and `CollectionsProvider` own all user-collection state. No component manages collection state locally.
- Components are purely presentational where possible. Data fetching and filtering happen in `App.tsx` or service hooks, not inside `GameCard` or `FilterBar`.

---

## 3. Adding a New Data Source

Follow this checklist in order. Do not skip steps.

1. Add a `SourceDef` entry to `source_registry.py` with correct `weight`, `is_primary`, `requires_pc`, `prior_count`, and `display_priority`.
2. Add the same `prior_count` value to `PRIOR_VOTE_COUNTS` dict in `sync.py`.
3. Create `integrations/<source>.py` — thin HTTP client, returns raw dict.
4. Create `integrations/<source>_service.py` — converts raw dict to `NormalizedGame` / `ExternalScore`.
5. Add the source call inside `refresh_game_sources()` in `sync.py`, guarded by `applicable_for_game()` if it has a `requires_pc` constraint.
6. Add a health-check entry to `provider_status.py`.
7. Update `frontend/src/types/game.ts` if new fields are exposed in the API response.
8. If the source is non-rating (price, popularity), weight = 0.0 and ensure it never enters `calculate_metrix_score()`.

---

## 4. Scoring Algorithm Rules

- The Bayesian formula is: `adjusted = (PRIOR_SCORE * prior_count + raw * review_count) / (prior_count + review_count)` where `PRIOR_SCORE = 70`.
- `confidence_level` tiers are: `Strong`, `Solid`, `Limited`, `Catalog`. Their definitions live in `sync.py`. Do not add new tiers without explicit user approval.
- The confidence formula is: `min(1.0, 0.15 + 0.35*coverage + 0.50*evidence)`. Evidence (review quality) outweighs coverage (source count). Do not rebalance these weights without approval.
- When changing the algorithm, always verify the output for known reference games before committing (e.g., Elden Ring, Stardew Valley, a console-only game, a low-review indie).
- Score weights across all primary sources must sum to 1.0. Verify after any weight change.

---

## 5. Frontend Rules

- **TypeScript strict mode** is on. Never use `any` as a type; use `unknown` and narrow it. Never cast with `as` unless absolutely unavoidable — if you do, add a comment explaining why.
- **CSS:** scoped styles in `.css` files co-located with components, or in `App.css` for global layout. No inline `style={{}}` for anything that isn't truly dynamic.
- **Color tokens:** use established CSS variables (e.g., `var(--color-accent-green)`) rather than hardcoded hex values. If a new color is needed, add it as a CSS variable first.
- **Icons:** use Lucide icons only (`lucide-react`). Do not import from other icon libraries.
- **View modes:** compact grid is the DEFAULT view. Any new card layout must preserve both `list` and `compact` modes.
- **Score ring colors:** green = Strong confidence, lime = Solid, amber = Limited. These map directly to `confidence_level`. Do not change the color mapping without updating both frontend and memory.
- **Sidebar:** adding a new top-level sidebar item requires user approval (keep it short). New filters go in `FilterBar`, not the sidebar.

---

## 6. API & Database Rules

- New API endpoints go in the appropriate `routers/` file. If no router fits, create a new one and register it in `main.py` with `app.include_router()`.
- All query parameters that filter game results must be validated via Pydantic in the route signature — never extracted from `request.query_params` manually.
- New DB columns always have a default value so existing rows are not broken on migration. Include `server_default` or `default` in the column definition.
- If you add a column to `models.py`, also add it to the relevant Pydantic schema in `schemas.py` if it should be API-exposed.
- Do not add `nullable=False` columns without a default unless you also write a migration that back-fills existing rows.

---

## 7. Code Style Rules

- **No comments** unless the WHY is non-obvious. A clear function name is better than a comment describing what it does.
- **No TODO comments** left in committed code. If something is deferred, note it in the user's memory system instead.
- **No magic numbers** inline — use named constants. Scoring constants go in `sync.py` at module level. UI layout constants go in CSS variables.
- **No duplicate logic** across integration files — if two sources need the same transformation (e.g., date parsing, score normalization), extract it to `types.py` or a shared utility.
- **No feature flags or backward-compat shims** — if something is replaced, delete the old code. The project is small enough that git history is the backward-compat layer.
- Function signatures: prefer explicit typed parameters over `**kwargs`. Service functions must never accept raw API dicts as parameters — they receive structured dataclasses.
- Keep `sync.py` functions focused. `calculate_metrix_score()` only calculates score. `refresh_game_sources()` only fetches and stores. Don't merge their responsibilities.

---

## 8. What Requires User Approval Before Implementing

- Any change to score weights, prior counts, or the confidence formula.
- Adding a new sidebar navigation item.
- Adding awards or recognition data as any form of numeric score input.
- Changing the `CollectionKey` enum values (breaks localStorage data for existing users).
- Introducing a new external API dependency (cost/rate-limit implications).
- Any database schema change that drops or renames existing columns.
- Changing the default view mode away from compact grid.

---

## 9. Task Completion Checklist

Before reporting a task as done:

- [ ] `backend/app/integrations/source_registry.py` is consistent with `sync.py` prior counts if touched.
- [ ] `frontend/src/types/game.ts` matches any new API response fields.
- [ ] No `any` types introduced in TypeScript.
- [ ] No hardcoded source name strings outside `source_registry.py`.
- [ ] `value_score` is not wired into `metrix_score` if price logic was touched.
- [ ] New DB columns have defaults.
- [ ] If the UI was changed: both `list` and `compact` view modes still work correctly.
