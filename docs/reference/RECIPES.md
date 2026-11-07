# Recipes (hand-written, 2026-11-07) — the usual changes, step by step

Each recipe lists the files to touch in order and the test to add. Exact line numbers: `SYMBOLS.md`, `API-ROUTES.md`, `FRONTEND-MAP.md`.

## Version bump (every change set, last step)
1. `.venv\Scripts\python app/bump_version.py` → sets `VERSION` / `RELEASED` in `app/backend/version.py`, adds `## <version> — HH:MM` to the top of `docs/Changelog.MD`.
2. Write the notes under that heading: what changed for people using the site / console, then what they must do (restart, wait for a re-read).
3. `python app/tools/reference/make_reference.py` so the generated reference files match. `tests/backend/test_version.py` checks the heading.

## New read-only API endpoint
1. `app/backend/api/<area>.py`: `@router.get("/path")`, pydantic query validation (`Query(..., pattern=…, le=…)`), raise `ApiError(404, "not_found", …)` for misses.
2. Wrap the body in `cached_response(request, "<key>", (args…), lambda: build())` from `backend/cache.py` if it is public and data-stamp dependent; use `cached(...)` for values.
   Anything that calls `auth.viewer / has_preview / has_console` becomes per-visitor (`private, no-store`) automatically.
3. Heavy answers (heatmaps, playback, compare, exports) cost 5 rate-limit tokens: add the path fragment to `guard.HEAVY` if it belongs there.
4. `app/frontend/src/api.ts`: type + `export const getX = (…) => request<T>(\`/api/...\`)`; `send()` for never-cached answers.
5. Test in `tests/backend/test_<area>.py` with `app_client(make_settings(tmp_path))`; pages send `X-EchoVR` + a browser UA when `scraper_guard=True`.
6. Document the route in `docs/Architecture.MD` (API table) if people will use it; regenerate `API-ROUTES.md`.

## New site write (rare; the site is read-only, D38)
1. Add the path prefix to `middleware.WRITES` (or `BOT` for secret-bearing scripts), otherwise the request is 405 before the router.
2. Check the visitor in the handler: `auth.has_console(request, fresh=True)` / own profile / bearer secret with `hmac.compare_digest`.
3. Log it (`admin_actions.log_command` for console-like actions) and add a test for the refusal path too.

## New per-match / per-player stat
1. `app/backend/stats/player.py` (accumulate per frame) or `stats/__init__.py` (match level); add the field to `stats/results.py`.
2. `app/backend/models.py` column + `persist.py` save. Nullable + `db.IN_PLACE_COLUMNS` keeps old matches visible while re-reading (D57); otherwise the derived tables are dropped and rebuilt.
3. Bump `STATS_VERSION` (`stats/__init__.py`) → every `done` replay is re-queued at the next start (hours on the NAS; old results stay visible).
4. Expose: `api/matches.py` (`_player_row`), `api/players.py` (profile aggregates), `api/leaderboard.py` (`STATS` table: key, label, higher_is_better, SQL expression), `downloads.py` (CSV columns).
5. Frontend: `api.ts` types, `MatchPage.tsx` columns + ⓘ help text, `PlayerPage.tsx` stat card, `LeaderboardPage.tsx` picks up `/api/leaderboard/stats` automatically.
6. Update `docs/DataModel.MD` (Derived / Profile set tables); test in `tests/backend/test_stats.py` with `replay_factory`.

## New achievement / challenge
1. `app/backend/achievements.py: _build_rules()` — add a `Rule(id, name, description, period, count=…, levels=…)`; ids are stable (next free id). The **description is the spec** (what players read must be what the code checks).
2. Icon: `app/frontend/public/achievements/<file>.png` + `icon_file()` mapping; theme / group in `app/frontend/src/components/AchievementsView.tsx: GROUPS / NEW_GROUPS`.
3. Rule text for the console export: `achievement_sheet.name_and_rule()` derives it; the Changelog states the new total ("replay challenges go from N to N+1").
4. Tests: `tests/backend/test_achievements.py` (one test per rule with a synthetic game that just reaches each medal). Medals are computed on request: nothing to migrate.

## New console command (website Console + admin.bat)
1. `app/admin_console.py`: `def cmd_<name>(sessions, …)` printing its result; argparse sub-command in `main()`.
2. `app/backend/api/console.py`: field(s) on `Args`, entry in `COMMANDS`; any new console phrase that names a command goes in `WEB_WORDING` (a test checks the pairs).
3. `app/frontend/src/pages/ConsolePage.tsx`: a button / form in the right tab calling `runConsole("<name>", args)`; risky ones get the confirm step.
4. Business logic in `backend/admin_actions.py`; audit log is automatic (`log_command`). Test in `tests/backend/test_admin_console.py`.

## New page or match-page tab
1. Page: `src/pages/<Name>Page.tsx` + `React.lazy` import and `<Route>` in `App.tsx`; `usePageTitle("…")`; add to `NAV` if it is top-level.
2. Match tab: `MatchPage.tsx: TABS` + render branch; keep the `?tab=` value stable (links are shared). Unknown `?tab=` values currently render nothing (Review, GUI-3).
3. Styles go in `styles.css` under a new section comment (`/* … */`) so `CSS-MAP.md` picks it up. Check phone width (390 px): tables need `className="stack"`.
4. Build check: `npm run build` (tsc + vite). No frontend tests exist; the browser sweep (`E2E-TESTING.md`) is the regression check.

## New setting
1. `backend/config.py: Settings` field + `from_env` (`ECHOVR_<NAME>`), docker-compose comment, `docs/Setup.MD` configuration table.
2. Tests pass it through `make_settings(tmp_path, <field>=…)`.

## Re-read triggers (what forces replays to be processed again)
- `PARSER_VERSION` change → all replays; `STATS_VERSION` change → all `done` replays; file size / mtime change → that replay; `admin reprocess / repair / reprocess-all`.
- `COMBAT_VERSION` (`backend/combat.py`) → combat reports; `tracks3d.FORMAT_VERSION` → 3D tracks rebuilt lazily on view (no reprocess, user preference).
- A changed replay root (`ECHOVR_REPLAY_SOURCE`) does **not** migrate rows: paths are relative to the root, so every file is "new" (Review, DATA-1).

## Local run with the Discord login bypassed
See `E2E-TESTING.md` (`app/tools/e2e/run_local.bat`, `local_login.py`).
