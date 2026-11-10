# Code map (hand-written, 2026-11-07) — entry points per area

Line numbers drift; `SYMBOLS.md` (generated) has the current ones. Paths are under `EchoVR-Replay-Stats/`.

## Runtime shape
- `run.bat` → `app/frontend` `npm run build` → `uvicorn backend.main:app --app-dir app` on :8000 (serves `app/frontend/dist`).
- `settings.local.bat` (not in git) is sourced by `run.bat` / `admin.bat` for env vars. Current local value: `ECHOVR_REPLAY_SOURCE=e:\ECRanked`.
- Threads inside the one process (`backend/main.py` lifespan): `Scanner` (share → `replays` rows), `Worker` (process pool, writes match data),
  `CombatIngest` (recorder `matches/*.json`), `arena.Tracker` (Nakama match list), `warm-caches`, `discord_names` refresh.
- **Every table is written by several threads**; SQLite WAL with Python's default 5 s busy timeout (`backend/db.py: open_db`). See Review.

## Parser — `app/parser/`
- `reader.py: open_replay(path, repair=…) -> ParsedReplay` (zip / plain detection, 1 MB chunk streaming, `UnsupportedReplay` / `CorruptReplay` / `IncompleteReplay`).
- `frames.py` line → `Frame` / `ReplayMeta` (add new JSON fields here **and** in `models.py`). `__init__.py: PARSER_VERSION` → bump = every replay re-read.

## Stats — `app/backend/stats/`
- `__init__.py: compute(meta, frames) -> MatchStats`, `STATS_VERSION` (bump = every `done` replay re-queued; D19).
- `player.py` per-player accumulator (speeds, arms, near-mate, deaths heuristic), `payload.py` (attacking team, winner, push / block),
  `maps.py` (map codes, bounds, minimap layouts), `results.py` dataclasses (what travels to `persist.py` and the remote worker).
- Position tracks are recorded during `compute` by `backend/tracks.py: TrackRecorder` (2 Hz, `tracks.bin`) and `backend/tracks3d.py` (5 Hz, `tracks3d.bin`).

## Import pipeline — `app/backend/`
- `scanner.py: scan_once / Scanner` — share → `replays` rows keyed by **path relative to `source_dir`** (changing the root duplicates the archive).
- `worker.py: claim_queued, analyse (pool), save_result, Worker._run` — newest `source_mtime` first, `priority_replays` first; crash recovery; `remote.py` for the PC worker.
- `persist.py: save_match / delete_match` — one transaction per replay; `duplicates.py` marks same-session copies (D13).
- `combat.py: CombatIngest, sync_once, _process` — recorder reports → `combat_*` tables (separate from replay data).
- `arena.py: Tracker` — polls `https://g.echovrce.com/status/matches`, fills `nakama_accounts`, `arena_*`, `nakama_combat_*`.

## Storage — `app/backend/db.py`, `models.py`
- `open_db` (pragmas, in-place column adds, stale-table rebuild), `DERIVED_TABLES`, `PRESERVED_TABLES`, `COMBAT_TABLES`, `IN_PLACE_COLUMNS`.
- `models.py`: 24 tables (list in `SYMBOLS.md`). `app_settings` holds every admin switch (challenge window, roles, remote mode, hidden stats, icon overrides).

## API — `app/backend/api/` (routes only; `API-ROUTES.md` lists them)
- Answer caching: `backend/cache.py: cached(request, key, args, build)` (values) and `cached_response(...)` (gzipped JSON + ETag, stale-while-revalidate).
- Errors: `backend/errors.py: ApiError(status, code, message)` → `{error_code, message}`; FastAPI validation errors are **not** wrapped (`{detail: [...]}`).
- Request gate: `backend/middleware.py: SiteMiddleware` (replay-file paths 404, non-GET 405 unless in `WRITES` / `BOT`, then `guard.check`) → `backend/guard.py` (UA + `X-EchoVR` + token buckets).
- Overview / home: `api/overview.py`; matches: `api/matches.py` (heatmap, playback, playback3d, export); players: `api/players.py`; leaderboard: `api/leaderboard.py`;
  achievements: `api/achievements.py` (+ ranking cache file `achievements-cache.pkl`; calculations run in the worker's side processes, `worker.run_side` lanes); combat: `api/combat.py`; arena / mega prizes: `api/arena.py`, `backend/mega_prizes.py`.

## Auth and staff — `app/backend/auth.py`, `api/auth.py`, `api/console.py`, `api/permissions.py`, `api/admin.py`, `api/profiles.py`
- `auth.enabled(settings)` needs client secret + bot token (+ ids). Session = signed cookie `echovr_session` (`auth.sign / unsign`, key `data/session.key`).
- `auth.allowed(settings, db, user_id, kind, roles)`: kind ∈ admin / console / preview; ids in `ECHOVR_DISCORD_PREVIEW_ROLES` always get console; others from `app_settings` via `admin_actions.discord_roles`.
- Console = `api/console.py: COMMANDS` dict → `app/admin_console.py: cmd_*` (same code as `admin.bat`), audit in `console_log`.
- Writes allowed on the site: icon PUT/POST, console POST, permissions POST, profile POST (own bio / avatar), bot `/api/bot/*` and worker `/api/worker/*` with bearer secrets.

## Admin console CLI — `app/admin_console.py`
- argparse sub-commands → `cmd_<name>`; business logic in `backend/admin_actions.py`, merges in `backend/aliases.py`.

## Frontend — `app/frontend/src/` (`FRONTEND-MAP.md` has exports + API calls)
- `App.tsx` routes + top bar; `api.ts` typed client + per-tab answer cache (`request()`, `send()`), **all requests add `X-EchoVR: 1`**.
- `useApi.ts` (`useApi`, `useWhileVisible`), `format.ts` (dates in viewer zone, numbers), `components/ui.tsx` (Skeleton, ErrorBoundary, FitText).
- Pages: `pages/*.tsx`; big components: `PlaybackView.tsx` (2D playback), `Map3D.tsx` (three.js; lazy chunk), `HeatmapView.tsx`, `Heatmap3DView.tsx`,
  `TimelineView.tsx`, `AchievementsView.tsx`, `ConsolePage.tsx` (1.4k lines: tabs = Dashboard / Players / Replays / Achievements / Audit log / Permissions).
- One stylesheet `styles.css` (4.1k lines, `CSS-MAP.md`); theme via `:root[data-theme]`; tables with class `stack` become cards < 760 px.
- Build: `tsc -b && vite build`; no linter / formatter / frontend tests. Keep CRLF and ~120-col lines.

## Tests — `tests/` (`TESTS-MAP.md`)
- `tests/app_helpers.py: make_settings(tmp_path, **overrides)`, `app_client(settings)` (TestClient with lifespan), `write(settings, {path: bytes})`;
  `tests/replay_factory.py` builds synthetic replays. Guard is off in tests unless `scraper_guard=True`; pages send `{"X-EchoVR": "1", "User-Agent": "Mozilla/5.0"}`.

## Ops
- `Dockerfile` (node build stage + python:3.12-slim), `.github/workflows/docker-image.yml` → `ghcr.io/vibinator/echocombat-replay-stats`, `docker-compose.yml` (NAS + cloudflared).
- `app/cloudflare_check.py` (`check_cloudflare.bat`), `app/remote_worker.py` (`remote_worker.bat`), `app/tools/backfill_tracks3d.py`, `app/tools/maps3d/` (GLB export),
  `app/tools/reference/make_reference.py` (these docs), `app/tools/e2e/` (local end-to-end runs).
