# CLAUDE.md — GameMetrix

Entry point for Claude Code on this repo. Read this first, every session.

## Read order

1. **This file** — how to work here.
2. **[AI.md](AI.md)** — the system map: architecture, data flow, where everything lives.
   Read it instead of exploring the codebase. It exists so you do not have to re-derive the
   architecture on every new conversation.
3. **[ai/AI_Guidelines.md](ai/AI_Guidelines.md)** — the rules. Invariants, code style, the
   "adding a source" checklist, approval gates, task checklist.
4. Only the specific files your task touches.

**Never trust the docs over the code.** Both files are hand-maintained and can drift. Before you
depend on a line, open the actual file. If you find drift, fix the doc in the same change.

Task-specific reading, on top of the above:

| Task touches | Also read first |
|---|---|
| scoring / weights / confidence | `backend/app/integrations/sync/scoring.py`, `source_registry.py`, `game_signals.py` |
| any API-exposed field | `backend/app/schemas.py`, `frontend/src/types/game.ts` |
| catalog filtering / sorting | `backend/app/services/game_query.py`, `frontend/src/catalog/config.ts` |
| background jobs / quotas | `backend/app/services/background.py`, `backend/app/config.py` |
| the game detail page | `frontend/src/pages/detail/`, and note it does **not** load `App.css` |

## Commands

```powershell
# backend
cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload      # http://127.0.0.1:8000
python -m pytest -q
python -m compileall app alembic

# frontend
cd frontend
npm run dev                                   # http://127.0.0.1:5173
npm run lint
npm run typecheck
npm run build
npm run test:e2e

# stack
docker compose config
docker compose up -d db
```

PostgreSQL is the only supported runtime database. Full command reference: `README.md`.

## Working rules

- **Verify before reporting done.** Backend change → `pytest -q`. Frontend change →
  `npm run typecheck` and `npm run lint`. Say plainly what you ran and what failed.
- **Stop and ask** before: changing score weights / the score formula / confidence tiers; adding
  a sidebar nav item; adding awards as any numeric score input; changing `CollectionKey` values;
  adding a third-party dependency or external API; dropping or renaming a DB column; changing the
  default view mode. Full list: `ai/AI_Guidelines.md` §10.
- **Never** put an `os.getenv` call outside `config.py`, hardcode a source name outside
  `source_registry.py`, feed `value_score` or awards into `metrix_score`, write a raw API response
  straight to the DB, or introduce `any` in TypeScript.
- **Schema changes are Alembic revisions** in `backend/alembic/versions/`. There is no
  `_run_migrations()` in `main.py` any more.
- Complete the whole task. If part of it is blocked, finish everything else and say exactly what
  you left out and why.
- Do not commit or push unless asked.

## End-of-task doc maintenance — required

Documentation drift is what makes the next session re-read the codebase. Before you report a task
complete, do this — it is part of the task, not an extra:

1. **Did this change make anything in `AI.md` false or incomplete?**
   Consult the trigger table in [`AI.md` §14](AI.md#14-doc-maintenance) — it maps each kind of
   change to the section that needs updating. Apply the edit now, in this same change.
2. **Did this establish a new rule, invariant or approval gate?**
   That goes in `ai/AI_Guidelines.md`, not `AI.md`. Keep the split clean:
   **AI.md describes what exists; AI_Guidelines.md dictates what you must do.**
3. **Did the architecture change?** Append one line to `AI.md` §15 (Change log), newest first:
   `- **YYYY-MM-DD** — what changed, in one sentence.`
   Skip this for cosmetic or single-file fixes.
4. **Did you discover something non-obvious that the code does not record?**
   A surprising constraint, a wrong assumption you made, a decision and its reason — that goes in
   memory (`memory/MEMORY.md` + a memory file), not into these documents.
5. **Did you find the docs already wrong?** Fix them, and mention it in your summary.

If nothing above applies, say so in one line rather than silently skipping it.

## Notes

- Conversations may be in Turkish; code, comments and documentation stay in English.
- `memory_bank/` holds older narrative notes. `AI.md` supersedes it for architecture — do not
  update `memory_bank/` as part of routine work.
