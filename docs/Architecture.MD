# Architecture

Last updated: 2026-11-01 — Beta 76 caching (stale-while-revalidate answer cache, ETag / 304, Cloudflare edge cache, D53).

## Stack
| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite (`app/frontend`) |
| Backend/API | Python 3.12+, FastAPI, Uvicorn (`app/backend`) |
| Parser | Pure Python package (`app/parser`); stdlib plus `orjson` for speed (optional: falls back to `json`, same result) |
| Storage | Replay originals: read-only share (`Z:\ECRanked\Replays`, D25). SQLite cache via SQLAlchemy 2.x under `data/` |
| Tests | pytest (backend/parser), Vitest (frontend, later) |

## Data flow
```
Replay share (read-only)  Z:\ECRanked\Replays\<map>\*.echoreplay   (~29k files, ~527 GB)
  │  Scanner thread: full scan on startup + every 5 min (os.scandir, ~4-8 s for 29k files)
  │    between full scans: every 15 s stat only the folders (~16 ms); a folder's modified time changed
  │      (file added / removed / renamed) → full scan now
  │    new path → insert replays row (queued); size/mtime changed → re-queue
  │    written < 2 min ago (modified, or created / changed: copies keep the old modified time) → skip until
  │      settled, full scan again as soon as the first one is old enough; share unreachable → change nothing
  ▼
Worker thread: claims queued rows, newest file first, up to N at a time (default 8)
  └─ ProcessPoolExecutor: analyse(path) = parser.open_replay + stats.compute (streaming, one pass)
  ◀─ result → save in one transaction: matches, players, match_players, loadouts, events
     replays.status = done | failed(+error_code, error_message)
  ▼
GET /api/... ← React pages (home, matches, match, players, player, import status)
```
- Startup re-queues `processing` rows, and `done`/`failed` rows from an older `parser_version`; `done` rows with an older `stats_version` (D19).
- Pool crash: in-flight replays re-queued and the pool restarted; a file in flight during 2 crashes → `failed` / `crashed`. Pool processes ignore Ctrl+C, so stopping never marks replays failed (they stay `processing` → re-queued next start).
- One writer: only the worker thread writes match data (SQLite).
- Restart (D27): results are kept in SQLite; the startup scan compares size + mtime only (no file reads), so finished replays are never re-read. Verified on the share: 95 / 95 finished replays untouched after a restart, 0 queued by the scan. While a replay is re-processed its old match stays visible (delete + save in one transaction).

## Modules
| Module | Responsibility |
|---|---|
| `parser/` | `open(path) -> ParsedReplay` (meta + frame iterator). Detects zip/plain, Combat vs other. Raises `UnsupportedReplay`, `CorruptReplay`, `IncompleteReplay`. `PARSER_VERSION`. No DB or web imports. Reads in 1 MB chunks (network share); lines orjson refuses, or with a user id beyond 64 bits, are parsed by `json`. |
| `parser/models.py` | Typed dataclasses: `Frame` (blue/orange player lists), `PlayerFrame`, `PayloadState`, `ReplayMeta` — only fields in ReplayData.MD. |
| `parser/frames.py` | Line → `(timestamp, dict)` → `Frame`/`ReplayMeta`. New API fields are added here + models.py. |
| `parser/reader.py` | Zip/plain detection, streaming, bad-line thresholds, size limit. `ParsedReplay.frames()` re-reads the file each call; `warnings` and `frame_count` are set when iteration ends. |
| `backend/stats/` | `compute(meta, frames) -> MatchStats` in one pass; one accumulator per stat group; `player.py` (per-player accumulator), `payload.py` (attacking team, winner, push/block), `results.py` (dataclasses), `maps.py` (map codes, old bounds D20). `STATS_VERSION`. No DB imports. |
| `backend/persist.py` | `save_match()` / `delete_match()`: MatchStats → rows; upserts `players` by user_id. Worker commits once, so a match is saved completely or not at all; a failure also removes the old match. |
| `backend/db.py`, `models.py` | SQLAlchemy engine/session + tables; schema created on startup; schema changes rebuild tables (DataModel Reprocessing). |
| `backend/scanner.py` | `scan_once()` syncs `replays` with the share; `Scanner` thread (interval, `scan_soon()`); `ScanState` for the import page. Never writes to the share. |
| `backend/worker.py` | `analyse()` (runs in pool), `save_result()`, `Worker` (claim newest-first, pool, crash recovery, `wait_idle()` for tests). |
| `backend/gear.py` | Loadout code → in-game name / cut flag (incl. old hex codes). |
| `backend/tracks.py` | 2 Hz position tracks: `TrackRecorder` (fed by `stats.compute`), binary encode/decode, `tracks.bin` per replay (DataModel). |
| `backend/heatmaps.py` | World → minimap cell mapping, line rasterising in numpy (D50; breaks on jumps > 12 m per sample), layer response. |
| `backend/api/leaderboard.py`, `downloads.py` | Leaderboard (incl. `stat=achievements`); CSV/JSON download responses. |
| `backend/admin_actions.py`, `aliases.py`; `app/admin_console.py` (`admin.bat`) | Every write: player merges (lossless, via reprocess), challenge period, reprocess / repair / scan / reprocess all, hiding replays that cannot be repaired. The website is read-only (D38): the server answers 405 `read_only` to any non-GET request |
| `backend/api/overview.py` | Dashboard, activity, players seen, search |
| `backend/achievements.py` | 75 rules (old `stat.js` ids 5–79), `evaluate(games)` = best game / day / week / all-time progress, tiers. Pure functions. |
| `backend/api/achievements.py`, `imports.py` | Achievements API + achievement ranking (rebuilt in the background at most every `ECHOVR_CACHE_REFRESH_S`, 10 min while importing; Python's cycle collector paused while it builds; calculated in the worker's helper processes, not in the web server's threads, see `_elsewhere`); Import status with per-stage breakdown. |
| `backend/cache.py` | Answer caches (D53): `cached()` (values) and `cached_response()` (JSON kept gzipped with a weak ETag, 304 on `If-None-Match`). Stale-while-revalidate on the data stamp (read at most every 2 s): an out-of-date answer is sent at once and rebuilt in the background (2 at a time) once `ECHOVR_CACHE_REFRESH_S` old; only a never-built answer waits, one build per key. `X-EchoVR-Cache` = HIT / MISS / STALE |
| `backend/middleware.py` | One pure ASGI layer for every request: replay files refused, read-only site, scraper guard; security headers; cache headers: per-visitor answers (auth.viewer asked, /api/auth, /api/admin) `private, no-store`, errors `no-store`, other API answers `no-cache` for browsers + `Cloudflare-CDN-Cache-Control: max-age=ECHOVR_EDGE_CACHE_S` (not STALE ones); index.html `no-cache`, /assets a year, other files 4 h |
| `backend/combat.py`, `backend/api/combat.py` | **Combat stats** (user, 2026-11-04), completely separate from the replay data: own tables (`combat_files`, `combat_matches`, `combat_players`, rebuilt on their own, `db.COMBAT_TABLES`), own reader, own endpoints. Collected like the replays: the recorder folder is mounted read-only (`ECHOVR_COMBAT_SOURCE`, default = the folder above the replay share), `CombatIngest` lists `matches/*.json` (stat of the folder every `ECHOVR_COMBAT_SCAN_S`, full list every 5 min), skips files written in the last `settle_s`, reads new / changed ones (size + mtime + `COMBAT_VERSION`) in one transaction each. Reports are small and complete (the event-log totals are inside), so no process pool. Ids stay text; `events` null = no event log (unknown, not 0); damage taken is never shown (spectators do not get it). Players are joined by `userid` and follow merges (`player_aliases`) at query time |
| `backend/api/` | Routes only; pydantic response schemas. |
| `backend/db.py`, `backend/tracks.py` (RAM) | D49: database memory-mapped + warmed at startup; `tracks.read()` keeps decoded files in an LRU (`set_cache_limit`, from `main.py`) |
| `backend/guard.py` | Scraper protection (D48): AI crawlers refused, `/api` only with the `X-EchoVR` header (sent by `api.ts`) and a browser user agent, per-visitor rate limit. Applied by `middleware.py` |

## Validation (import)
| Check | Rule | Result |
|---|---|---|
| Extension | `.echoreplay` (case-insensitive), any subfolder of the share | other files ignored |
| Settled | not modified in the last 2 min | skipped until a later scan |
| Container | zip (`PK\x03\x04`) or plain text; first `*.echoreplay` zip entry only; ≤ 1 GB uncompressed | else `corrupt` |
| Content | `match_type == "Echo_Combat"`; ≥ 2 readable frames | `unsupported` / `incomplete` |
| Read error | network / permission problem | `unreadable` (retried after a parser upgrade or reprocess) |

## API (v1)
All JSON. No upload, delete or replay-download endpoints: replays come only from the share (D25, D28). IDs are integers except `user_id` (string). List endpoints take `limit` (default 50, max 200) and `offset`, and return `{items, total}`.

| Method | Path | Purpose | Phase |
|---|---|---|---|
| GET | /api/overview | Home dashboard: totals, today / week, by map, top players this week, latest; `global` = top weapon / ordnance / tac mod (time share), recorded hours, avg / longest match, players per match, deaths (est.), fastest, most active, busiest day, payload attack win rate, capture wins | D37 |
| GET | /api/overview/activity | Matches per `bucket` (day / week / month / year), with a per-map split (`maps`) for the stacked chart; `day` = the 90 days up to the newest match, empty days included | D37 |
| GET | /api/overview/players-seen | Distinct players per hour (24h) / day (7d, 30d); `anchor` now / latest match | D37 |
| GET | /api/overview/map-heat | All-time heat per map for the home page's map cards, as palette PNG data URLs over the minimaps; `layer` = `team` or `weapon:` / `ordnance:` / `tacmod:<code>` (`layers` lists them). Gear: `view` = `favoured` (held there more often than on the map as a whole, the default) or `all`. Also `hand:left` / `hand:right` (arm setting, from the database), `pose:upside` / `pose:upright` (head roll in `tracks3d.bin`: only matches that have it) and, on payload maps, `payload:speed` / `payload:moving` / `payload:back` (a band along the route, from the payload distance series). Further `speed:<band>`, `death:all` (estimated deaths, smoothed; favoured = per time spent there). The answer carries `read` (what a palette entry means, for the page's read-out under the pointer) and per map `top` / `average`. `days=30|90`: only matches started in the last so many days (own counts file `map-heat-30d.npz`, updated daily, held in memory only while asked for). `against=<layer>` (also `team:blue` / `team:orange`) compares two layers, each in its own colour where it is relatively more often. Counts kept in `data/database/map-heat.npz`, brought up to date once per calendar month in the background (`map_heat.py`) | D37 |
| GET | /api/search | `q`: players by name (merged ids left out, D34) + match by `#id` | D37 |
| GET | /api/health | `{status, parser_version, stats_version, source_dir}` | 3 |
| GET | /api/import | `{source_dir, workers, busy, counts, redo (re-processing after update), versions, rate_per_min (last 10 min), eta_min, matches_by_map, stages[{key, label, done, total, detail}] (files → replays → matches → players → events → tracks → heatmaps → leaderboard → achievements), current[{replay_id, source_path, seconds}], scan{…}}` | D25 |
| GET | /api/replays | List replays (newest file first); filter `status` | 3 |
| GET | /api/replays/{id} | `source_path`, status, error, warnings, `match_id` (also in list items) | 3, 5 |
| GET | /api/matches | List; filters `map`, `mode`, `player` (user_id), `player_name`, `from`/`to`, `private`, `min_players`, `result` (blue / orange / attack_win / defence_win / unknown); `with_players` adds names (cards) | 6, D37 |
| GET | /api/matches/{id} | Match + teams + per-player stats (derived % included) + loadouts + `also_recorded_in` (other copies of the same match) + `duplicate_of` (set: that copy counts in stats instead, D13) + `has_combat` (a recorder report exists: the page asks for the Combat tab only then) | 6 |
| GET | /api/matches/{id}/events | Timeline; filter `type` | 6 |
| GET | /api/players | Search; `q` (name contains, case-insensitive), paging; items include games, last_seen_at | 6 |
| GET | /api/players/{user_id} | A merged id answers with its main player (`user_id` = main; the page moves there). Profile stat set (DataModel; `period`=day\|week\|month\|all, `map`) + wins/losses + level + loadout usage + 20 recent matches (with team, result) | 6 |
| GET | /api/leaderboard | Rank players by `stat` (see `/stats`; `loadout` + `weapon`/`ordnance`/`tacmod` = hours used); `period`, `map`, `private`, `min_games` (default 10), paging. Lower-is-better stats (ping, deaths, idle) sort ascending | 7 |
| GET | /api/leaderboard/stats | Selectable stats `[{key, label, higher_is_better}]` | 7 |
| GET | /api/leaderboard/gear | Loadout codes + names (released first, then cut) | 7 |
| GET | /api/matches/{id}/timeline | `{hz, duration_s, series{blue_points, orange_points \| payload_distance}, events}`; series empty for old-format replays | 7 |
| GET | /api/matches/{id}/heatmap | `mode` team / weapons / ordnance / tacmod / loadout / speed, `cell` 0.1 only (`heatmaps.CELL_SIZES`; the coarser 0.25 / 0.5 / 1 were dropped with the 0.1 m heatmaps), `player`. 404 `no_tracks` until processed | 7, D35 |
| GET | /api/matches/{id}/playback | Positions per player at 2 Hz in image space (u, v, team) | D37 |
| GET | /api/matches/{id}/playback3d | Head position (dm), facing (yaw 0–255, pitch °), team and hands (relative to the head, 2 cm steps) per player at 5 Hz in world space, payload cart position, payload route / capture point in metres, play extent, map model URL (`/maps3d/<map>.glb?v=<release>`, cached for good). From `tracks3d.bin`; a match without one (processed before 3D playback) gets it built on first view in the worker's low-priority processes (~1 s; 503 `tracks3d_building` after 25 s, 404 `no_tracks3d` when the replay cannot be read) | 3D playback |
| GET | /api/players/{user_id}/heatmap | `map` (required), `mode` = the match modes + deaths, `period`, `last` (default 200, max 5000), `cell`. Cached per data stamp | 7, D35 |
| GET | /api/players/{user_id}/trends | Per week / month / year: games, win rate, deaths/game, avg + top speed, ping | D37 |
| GET | /api/players/{user_id}/companions | Most frequent teammates / opponents with record | D37 |
| GET | /api/players/compare/{id,id,…} | 2–4 profiles + head-to-head of the first two | D37 |
| GET | /api/players/{user_id}/achievements | `{overall, completed, total, items[{id, name, description, period, icon, estimated, progress, tier}]}` (D31) | 8 |
| GET | /api/achievements | Catalogue + rarity (`unlocked_share`, `completed_share` of players with 10+ games) | 8, D37 |
| GET | /api/achievements/recent | Latest completions (players active in the archive's last 30 days) | D37 |
| GET | /api/admin/achievements, /api/admin/achievements.xlsx, /api/admin/icons | Admin tab (Discord admin role): achievement list with how to get it and current / default icon, the same as Excel, icon choices | D42, D43 |
| PUT, POST | /api/admin/achievements/{id}/icon | Choose an icon `{icon}` (null = default) / upload a PNG (raw body). Needs header `X-EchoVR: 1`; the only writes the website accepts | D43 |
| GET | /achievements/custom/{hash}.png | Uploaded icons | D43 |
| GET | /api/auth/me, /login, /callback, /logout | Discord login for previews: `{enabled, user: {name, preview}}`; login / callback / logout redirect | D41 |
| GET | /api/challenges | Flamingo Challenge period `{start, end, launched, preview, active}`; `preview` = this visitor has the Discord preview role; `launched` = start date reached. Before it the achievement endpoints (and `stat=achievements`) answer 403 `coming_soon` | D33, D40 |
| GET | /api/combat/summary, /stats, /players/{user_id}, /leaderboard, /matches, /matches/{session_id} | Combat stats (combat.py): totals, K/D, damage per minute, per map, shots / kills / deaths per weapon, tac mod use, heal bubbles, stuns (matches with an event log; `events_incomplete` = log ended early), leaderboard by stat, combat match list / detail. `period`, `map`, `min_games` as the Leaderboard | 2026-11-04 |
| GET | /api/matches/{id}/export?format=csv\|json | Match download: CSV = one row per player; JSON = match detail | 7 |

Heatmap response: `{map, image: "/minimaps/<map>.png", cols, rows, cell_m, matches, layers: [{key, label, packed: {d, n, w}, max}]}` — cells are in minimap image space (layout per map in `stats/maps.py`, ReplayData). `packed` (2026-11-01, a third of the old `cells: [[col, row, count]]` size): cells sorted by index `row * cols + col`; `d` = base64 little-endian uint32 differences between consecutive indices (the first from 0), `n` = base64 counts, uint16 (`w` = 2) or uint32 (`w` = 4). `heatmaps.unpack_cells` / `unpackCells` (api.ts) decode it.

### Response sketch — `GET /api/matches/{id}`
```json
{
  "id": 12, "replay_id": 15, "session_id": "BF48D570-...",
  "map": "surge", "mode": "payload", "started_at": "2026-10-28T20:45:44",
  "duration_s": 517.7, "frame_rate_hz": 19.6,
  "score": {"blue_rounds": 0, "orange_rounds": 0, "payload_checkpoint": 3, "payload_distance": 206.8},
  "winner": null, "contested_s": 0.0,
  "teams": {
    "blue":   [{"user_id": "1324398816765673576", "name": "…", "play_time_s": 512.3, "left_early": false,
                "avg_ping": 61, "avg_speed": 4.2, "top_speed": 17.9, "pct_stopped": 0.12,
                "pct_upside_down": 0.03, "pct_near_mate": 0.21, "pct_near_enemy": 0.08,
                "dominant_arm": "Right", "deaths_est": 7,
                "loadouts": [{"weapon": "smg", "tacmod": "sensor", "ordnance": "det", "share": 0.64}]}],
    "orange": []
  },
  "also_recorded_in": [16]
}
```

## Error handling
- API errors (e.g. 404 `not_found`, `file_missing`, 409 `busy`) → body `{error_code, message}`. Validation errors are 422 `bad_request` with the same shape (`message` = the first problem, `detail` = the list); an id beyond 64 bits is 404 (`errors.py`).
- SQLite has one writer at a time and several threads write (worker, combat reports, arena poll, scanner, console): a writer waits up to `db.BUSY_TIMEOUT_S` (30 s). If it still fails, a replay result goes back to `queued` and a combat report is read again next scan; nothing is marked failed for a busy database.
- Parse/stats failures stored on the replay row and listed on the Import page; nothing partial is persisted (single transaction).
- Same `sessionid` in several files → separate matches with `also_recorded_in` (D13).
- Unknown map code → `map = "unknown"`; bounds-based stats skipped (deaths_est = 0, frames_in_bounds = frames_present); mode from fields present.
- Share offline → scan changes nothing; pages keep working; downloads return `file_missing`.

## Frontend pages
| Page | Route | Notes |
|---|---|---|
| Home dashboard | `/` | Totals, most popular gear, global stats, matches per map (minimap cards with the all-time heatmap: teams, or one weapon / ordnance / tac mod; a card's picture opens that map large), players seen (24 h / 7 d / 1 month), activity per month / year, most active this week, latest match cards |
| Matches | `/matches` | Cards or list; filters map, mode, result, public/private, min players, dates, player name (all in the URL) |
| Match | `/matches/:id?tab=` | Scoreboard (teams side by side), highlights, tabs Players / Timeline / Heatmap (mode, player, detail; zoom, opacity, side by side) / Playback; CSV/JSON export |
| Players / Player | `/players`, `/players/:userId` | Profile header (level, seen, main loadout, favourite map, form), Compare, stat cards with ⓘ help, trends (small multiples), teammates / opponents, heatmap (settings in URL), achievements summary, recent matches |
| Compare | `/compare?players=a,b,…` | Up to 4 players, best value highlighted, head-to-head, heatmaps side by side |
| Combat stats | `/combat`, `/combat/:id`; "Combat stats" section on the player page | The game's own counters from the recorder's match reports, separate from the replay stats |
| Leaderboard | `/leaderboard` | Podium, rank change vs previous period |
| Achievements | `/achievements[?player=]` | "Coming soon" until the start date (D40); then challenge-period banner, rarity, recently completed, closest-to-complete sort |
| Import | `/import` | Stages, throughput chart, progress per year, live files, failed files with **Repair** / Repair all |

Layout: sticky top bar (ECRanked background) with nav (Matches, Players, Leaderboard, Achievements, Compare, Import; collapsible on phones), global search (`/` to focus), light/dark toggle; footer with Admin link. Tables with `class="stack"` become cards under 760 px + footer credit line. No login, upload, delete or replay-download UI.

Charts: `TimelineView` (SVG line chart, crosshair tooltip, legend for 2 series, key-moment markers; series colours `#12a6c4` / `#d96a1a` pass the dataviz validator on `#1f2228`), `HeatmapView` (canvas over the minimap, one hue per layer with log-scaled alpha, layer toggles, hover counts, table view). Weapon layer colours = validated dark categorical order, fixed per weapon code. Minimaps served from `app/frontend/public/minimaps/<map>.png` (low-res copies).

Dev: Vite on :5173 proxies `/api` to Uvicorn on :8000. Production: FastAPI mounts `app/frontend/dist` at `/` when it exists. Pages other than home are loaded on first visit (`React.lazy`); `/assets/*` (hashed names) are sent with a 1-year immutable cache header. Cached answers are orjson + gzip level 6 once per build (cache.py); other responses are gzipped at level 4. Import pool processes run at lower CPU priority (nice 10 / below normal) so requests win when both want the CPU.

Frontend code (`app/frontend/src`): `api.ts` (typed API client + answer cache: reused 60 s without asking, older answers up to 1 h shown at once and refreshed in the background, kept per tab in sessionStorage under the build id unless `no-store` or > 150 KB; 30 s timeout, one retry for GET on network errors / 5xx; STALE answers re-checked after 3 s; `connection` = server unreachable note in the top bar), one component file per page, `styles.css` (plain CSS, team colours as variables). `useApi` re-renders a page when a background refresh changed an answer it shows; `useWhileVisible` polls only in visible tabs; `WhenVisible` loads sections far down a page when scrolled near. Import page polls every 5 s. Routing: `react-router` (`App.tsx`); pages in `src/pages/`, shared table/badge/gear components in `src/components/`, `useApi.ts` (fetch hook), `format.ts` (display formatting). FastAPI serves `index.html` for any non-API path so deep links work (`SinglePageApp` in `main.py`).

## Deployment
- v1: local only, single user, no auth, binds to 127.0.0.1. `run.bat` (project root) = first-run setup + build + start + open browser.
- Must run in a session that can see the share (mapped `Z:`), or set `ECHOVR_REPLAY_SOURCE` to the share's network (UNC) path, e.g. `\\<server>\<share>\Replays`.
- First full import ≈ 3 h at 8 workers (measured 2.5 replays/s); `ECHOVR_WORKERS` raises it (24 cores; network may become the limit).
