# docs/reference — start here before editing anything

Small, dense files meant to be read **instead of** the source when planning a change, so a change costs the tokens of
one or two files, not a tour of the codebase. Added 2026-11-07 (end-to-end review).

| File | What it answers | Kept up to date by |
|---|---|---|
| `CODE-MAP.md` | "Where does X live, and what are the 3–5 functions I will touch?" per area (parser, worker, stats, API, auth, console, frontend) | hand-written; update when a module is added or renamed |
| `RECIPES.md` | Step lists for the common changes: new endpoint, new stat, new achievement, new console command, new page / tab, new setting, version bump, re-read triggers | hand-written |
| `E2E-TESTING.md` | How to run the site locally with the Discord login **bypassed**, and the API / browser sweeps under `app/tools/e2e/` | hand-written |
| `SYMBOLS.md` | Every Python file: line count, purpose line, top-level functions / classes with line numbers | **generated**: `python app/tools/reference/make_reference.py` |
| `API-ROUTES.md` | Every HTTP route: method, path, handler, `file:line`, purpose | generated |
| `FRONTEND-MAP.md` | Every React file: exports with line numbers, which `api.ts` calls it makes; `api.ts` function → endpoint | generated |
| `CSS-MAP.md` | Section comments of `styles.css` with line numbers | generated |
| `TESTS-MAP.md` | Every test file and its test names | generated |
| `echocombat-extract.md`, `gear-table.json`, `minimaps/` | Old-site reference material (Phase 1) | historical |

Workflow for a change:
1. Read `CODE-MAP.md` (area) → `RECIPES.md` (the matching recipe) → `SYMBOLS.md` / `API-ROUTES.md` / `FRONTEND-MAP.md` for the exact lines.
2. Open only those lines with `Read(offset, limit)` or `sed -n`.
3. After the change: `pytest -q`, `npm run build`, `python app/tools/reference/make_reference.py`, `python app/bump_version.py` + Changelog entry
   (see `RECIPES.md` → Version bump).

Long-form docs (why things are the way they are): `../Architecture.MD`, `../DataModel.MD`, `../Decisions.MD`, `../Setup.MD`,
`../CombatStats.MD`, `../ReplayData.MD`, `../WebReplayer-Review.MD` (3D playback). The review that produced these files:
`../Review-2026-11-07.MD`.
