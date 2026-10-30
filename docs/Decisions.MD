# Decisions

| ID | Date | Decision | Alternatives | Reason | Impact |
|---|---|---|---|---|---|
| D1 | 2026-10-29 | Server-side parsing | Browser, both | One pipeline; easy persistence/aggregation | Requires local backend |
| D2 | 2026-10-29 | Python FastAPI backend + Python parser | Node/TS, .NET | Good binary/zip tooling; simple API | Two languages (Py + TS) |
| D3 | 2026-10-29 | React + Vite (TS) frontend; SQLite | Server-rendered; Postgres | Simple, modern, zero-config DB | Postgres migration later if needed |
| D4 | 2026-10-29 | Keep original replay files | Delete after parse | Allows re-parsing when parser improves | Superseded by D25: originals stay in the share |
| D5 | 2026-10-29 | No user accounts in v1 | Simple login | Local single-user tool | Add auth before any public deploy |
| D6 | 2026-10-29 | Reference code may be read directly (read-only) | Pasted extracts only | User approved; faster discovery | Reference folders never modified |
| D7 | 2026-10-29 | Scope v1 to Echo Combat `.echoreplay` (zip and plain text) | Also Arena | All samples and the old app are Combat | Arena files rejected as `unsupported` |
| D8 | 2026-10-29 | Identify players by `userid` (stored as TEXT) | name, slot | Names change, slots reused; userid > 2^53 breaks JS numbers | API returns userid as string |
| D9 | 2026-10-29 | Do not support legacy `.ecrreplay` (bz2 pickle) | Unpickle | Unpickling untrusted files executes code | Old archives need offline conversion |
| D10 | 2026-10-29 | Store per-player numerator/denominator counts, compute % at query time | Store percentages | Exact aggregation across matches (as old app did) | Slightly more columns |
| D11 | 2026-10-29 | Positions not stored in DB; downsampled tracks file per replay in `data/processed/` | Frames table | Millions of rows per match otherwise | Heatmaps/timeline read a file |
| D12 | 2026-10-29 | Record `parser_version` + `stats_version`; reprocess endpoint | Re-upload | Stats rules (deaths heuristic) will change | Derived rows deleted + rebuilt on reprocess |
| D13 | 2026-10-29 | Same `sessionid` in several files → separate matches, flagged as duplicates | Merge | Merging overlapping recordings is complex | UI shows "also recorded in…" |
| D14 | 2026-10-29 | Player URLs keyed by `user_id`; name search resolves to it | `/user/{username}` (old site) | Names change and are not unique (D8) | Old profile links not reproducible |
| D15 | 2026-10-29 | Leaderboards reclassified Defer → Simplify (Phase 7) | Keep deferred | Old profile showed pub leaderboards; it is just the aggregate query ranked | One extra endpoint + page; no new tables |
| D16 | 2026-10-29 | No dependency on `ecranked.ddns.net` API/websocket | Proxy / revive | Offline; all data comes from uploads | Old hosted data not recoverable by the app |
| D17 | 2026-10-29 | Achievements computed at query time from match_players + loadouts; day/week = calendar periods in recorder local time | Stored progress table (old) | Rebuildable, no incremental state; old app used resetting daily/weekly tables | Thresholds follow the rule text, not old code constants (user, 2026-10-29) |
| D18 | 2026-10-29 | Heatmaps drawn in the browser (canvas); match = raw tracks, player = server-summed 0.5 m grid per map, cached | Pre-rendered PNGs via job queue (old) | No queue, instant, re-colourable; many matches stay cheap as grids | Grid cache cleared on upload/delete/reprocess |
| D19 | 2026-10-29 | Re-process automatically on startup when `parser_version`/`stats_version` differ | Manual reprocess only | Parser/stats fixes reach old uploads without user action | Startup may spend a few seconds per replay after an upgrade |
| D20 | 2026-10-29 | Keep the old app's map bounds for in-bounds stats and deaths | Heatmap extents (fit positions better) | User: numbers stay comparable with old ECRanked | Combustion/fission/surge in-bounds % and deaths kept as old app computed them; extents still used for heatmaps |
| D21 | 2026-10-29 | Payload winner, attacking team and push/block time from `payload` + player proximity (3 m) | Leave payload winner unknown | Data supports it; fills the match result gap | Marked estimated; rule may need revisiting if teams swap sides |
| D22 | 2026-10-29 | Top speed must be held for a full 1 s; window resets on death | Copy old frame-count buffer | Avoids spikes and stale pre-death samples | Differs from old app in 2 / 16 sample players (≤ 0.29 m/s) |
| D23 | 2026-10-29 | Derived-table schema changes handled by drop + rebuild, not migrations | Alembic now | All derived data is rebuildable (D4, D19) | Restart after upgrade reprocesses every replay |
| D24 | 2026-10-30 | Exclude ping = 999 (placeholder) from average ping | Average it in (old app) | Not a real reading; inflated one sample player's average from 31 to 58 ms | Avg ping differs from old app only for players with 999 frames |
| D25 | 2026-10-30 | Replays come only from the read-only share `Z:\ECRanked\Replays` (29k files, 527 GB): auto scan on startup + every 5 min, processed in parallel (8 processes) newest first; files read in place, never copied or written | Web upload; copy into `data/uploads` | User request; copying 527 GB is impractical | No upload/delete UI or API; DB is a rebuildable cache; needs the share online to (re)process and download. Supersedes D4 (copy originals) |
| D26 | 2026-10-30 | Game mode from the map, not from fields present | Infer from `payload` block | Replays before ~2022 Q4 have no payload block, so payload maps were mis-classified | Old payload matches show mode payload with winner unknown |
| D27 | 2026-10-30 | Imported results persist across restarts: a file is re-read only if its size/mtime changes, it was mid-processing, or the parser/stats version changes; version-triggered reprocessing runs in the background while old results stay visible. Future `replays`/`players` schema changes ship with a migration, not a wipe | Re-scan + re-parse on every start | User: restarts must not reload ~29k files (≈ 3 h) | Restart cost = one share listing (≈ 8 s) |
| D28 | 2026-10-30 | No replay download on the website (endpoint removed too) | Keep download | User request | Originals only reachable on the share |
| D29 | 2026-10-30 | Heatmap world→image layout per map verified by plotting sample positions; use only the low-res minimaps | Trust old extents; high-res images | Surge is z-down, combustion rotated 90°; dyson/combustion high-res images are mirrored vs low-res | `HEATMAP_LAYOUTS` in `stats/maps.py` |
| D30 | 2026-10-30 | Tracks stored as compact binary (int16 dm x/z, 2 Hz) instead of JSON xyz | JSON per D11 | ≈ 0.6 GB vs several GB for 29k matches | Needs `tracks.py` to read; y (height) not kept |
| D31 | 2026-10-30 | Achievement interpretation: "use only X" = X ≥ 95 % of the game's loadout time, counted per game; "used" = ≥ 5 % (old cutoff); per-game rules need ≥ 3 min played; all-time averages ramp over the first 50 games; ids 55–66 (no title in old code) named "<Gear> Veteran: play 100 games using <gear>"; ids 0–4 unused | Copy old per-day aggregate logic | Rule text says "games"; avoids trivial 10-second achievements; old code had no names for 55–66 | 75 achievements; a few (35 m/s top speed) may be unreachable with the held-for-1-s top speed |
| D32 | 2026-10-30 | Import page shows a per-stage breakdown (files → replays → match stats → players → events → position tracks → heatmaps → leaderboard → achievements), live files, rate and time left | Counts only | User request | `matches.has_tracks` column; `Worker.current()` |
| D33 | 2026-10-30 | Admin = one server password (`ECHOVR_ADMIN_PASSWORD`, header `X-Admin-Password`, kept in the browser tab only); admins set the Flamingo Challenge period (start / end date; only matches inside count) | Accounts | Smallest secure step beyond D5 | Admin disabled when the variable is unset; settings in `app_settings` (kept across rebuilds) |
| D34 | 2026-10-30 | Player merge is a rule (`player_aliases`) applied by re-processing the affected replays; undo deletes the rule and re-processes again; alias + main in one match stay separate; a failed re-read keeps the previous results | Rewrite rows in place | Lossless and exactly reversible (user requirement) | Merge / undo take minutes for big players (prioritised in the queue) |
| D35 | 2026-10-30 | Heatmaps: 0.25 m cells by default (0.5 / 1 m selectable); high-res minimaps, each oriented by checking real positions + team spawn sides; layers by team, weapon, ordnance, tac mod, full loadout (top 7 + Other) or speed band; tracks format v2 adds ordnance + tac mod | 0.5 m, low-res images | User request | Stats v7 → one more full reprocess; low-res dyson image had swapped team colours (corrects D29) |
| D36 | 2026-10-30 | Repair (salvage) mode for failed replays, from the Import page: damaged zips are inflated straight from the local header up to the damage, unreadable lines (incl. the first) skipped without limit; the share is never written; the request (`repair_requests`) is kept across rebuilds | Leave damaged files failed | User request | Repaired matches carry a "Repaired: …" warning and tag; unsupported (non-Combat) and unreadable (I/O) files are not repairable |
| D37 | 2026-10-30 | GUI round 2: ECRanked look (Montserrat, combat background), light / dark theme (chart colours validated per theme), mobile menu + stacked tables, global search (`/`), dashboard home, match cards + filters, scoreboard + highlights, playback, heatmap zoom / opacity / side-by-side, profile header + trends + teammates, compare page, leaderboard podium / rank changes / pinned "my player" (localStorage), achievement rarity / recent / closest, admin page, import throughput + per-year | — | User request (all 20 ideas) | Montserrat loads from Google Fonts (falls back to system font offline) |
| D38 | 2026-10-30 | The website is read-only; every change (player merges, challenge period, reprocess / repair, scan, hiding replays repair cannot fix) is made in the admin console `admin.bat`, on the database directly. Replaces the D33 password and the Admin / repair / scan buttons | Admin page with a password | User request: admin tools outside the website | Server refuses non-GET requests (405 `read_only`); console-queued replays go first via `priority_replays`; hidden replays kept in `hidden_replays` (across rebuilds) |
| D39 | 2026-10-30 | Achievement logic follows the text on the website (hidden conditions written into the text); 21 new achievements (80-100, marked "new") from data the old site never used: unreleased gear, all gear in one game, wins / streaks, payload push / block, emotes. Older-API hex gear symbols normalised in the parser | Old stat.js thresholds | User request | Targets checked against the 2026 archive so each is reachable; Attack Drone / Overcharge / Umbral Veil / Neutron left out (35 games or fewer). Replays still holding hex codes are re-read once at startup |
| D43 | 2026-10-30 | Admins change achievement icons in the Admin tab: pick a built-in badge image or upload a PNG (max 512 KB, 1024 px, checked; stored by content hash in `<data>/icons`, served at `/achievements/custom/`); the choice is in `app_settings` (kept across rebuilds) and applied when answers are sent, never in cached results. The only write the website accepts (exception to D38): PUT / POST `/api/admin/achievements/{id}/icon`, Discord admin role + `X-EchoVR` header | Icons only in admin.bat | User request | Cross-site requests cannot add the header (CORS preflight refused) and the login cookie is SameSite=Lax |
| D42 | 2026-10-30 | Admin tab on the website for Discord members with an admin role (picked in admin.bat option 15 / `admin-roles`): every achievement with how to get it and an Excel download, both built from the live rules on each request so they always match the site. Admins also get the preview | Static Excel file in docs | User request: a link that stays current | Adds openpyxl; read-only apart from icons (D43) |
| D41 | 2026-10-30 | Preview access before the launch: "Log in with Discord" (OAuth2 `identify` only, user token revoked at once); the bot token checks the member's roles in server 779349159852769310 (cached 5 min); session = signed cookie (`data/session.key`), nothing stored in the database. Previewers count every match in the archive until the launch | Per-person preview links; user-token role check (`guilds.members.read`) | User request; the community and roles live on Discord, access cannot be forwarded | Off until secret + bot token are set; preview roles picked in the admin console (`app_settings`, kept across rebuilds) or `ECHOVR_DISCORD_PREVIEW_ROLES`; login is the only per-visitor state, those API answers are `Cache-Control: private, no-store` |
| D40 | 2026-10-30 | Achievements and challenges launch on the challenge start date set in the admin console: until then (no start date, or one still to come) the website shows "Coming soon" and the achievement API answers 403 `coming_soon`; from it on, only matches from that date count | Always public, counting the whole archive | User request | The start date is now required to show anything; the end date stays optional (open-ended) |

## Feature classification (old app)
| Feature | Class | Reason |
|---|---|---|
| Per-match "skim" stats (play time, ping, speed, top speed, stopped, upside down, near mate/enemy, arm, deaths, crashed) | Retain | Core value; all derivable |
| Loadout usage (64-bucket encoded dict) | Simplify | Store raw codes + frame counts; display names from `gear.py` at query time (cut gear flagged) |
| Deaths via out-of-bounds heuristic | Retain (flagged) | Only death signal available; mark as estimated |
| Match list (recent, random, all, count) | Simplify | One list endpoint with sort/filter/paging |
| Match detail (skim JSON) | Retain | Match detail page |
| Replay download | Remove | User request (D28) |
| All-time per-player stats | Retain | Aggregation query over match_players |
| Daily / weekly / monthly stat tables | Simplify | Date-range filter on the same aggregate query |
| Match heatmap: all players / one team / one player, distinct colour per player | Retain → Phase 7 | Client-side canvas from tracks file (D18) |
| Player heatmap per map, coloured by team | Retain → Phase 7 | Server grid over the player's tracks files (D18) |
| Player death-location heatmap | Simplify → Phase 7 | Points from `death_est` events (x, z stored) |
| Player weapon heatmap (colour per weapon) | Simplify → Phase 7 | Weapon per tracks sample; all weapon codes, not only 4 |
| Heatmap filters: date range, last N games | Simplify → Phase 7 | Same `period`/`from`/`to` + `last` params as profile |
| Heatmap "inverted" mode | Remove | Flag accepted but never implemented in old code |
| Heatmap blue/orange game balancing (equal games per side) | Remove | Team colouring shows sides instead |
| Adaptive resolution/saturation table; position interpolation; 240-frame skip after deaths | Simplify / Remove | Fixed 0.5 m cells, log colour scale, line segments broken on jumps; skip rule assumes 30 fps, purpose unclear |
| Minimap background images | Retain → Phase 7 | Found; copied to `docs/reference/minimaps/`; low-res for thumbnails, high-res for zoom |
| Heatmap job queue (MySQL `heatmaps` table, process pool, PNG files, Discord webhook) | Remove | On-demand rendering, no accounts |
| Timestamps CSV / teams over time | Simplify → Phase 7 | Covered by CSV/JSON export |
| Leaderboards (old stats: total games, inverted %, frames per loadout + own rank, achievement %; daily / weekly / monthly / all time) | Simplify → Phase 7 | Ranked aggregate query with date range (D15); any profile stat selectable |
| Achievements (80 + overall %; rules in `stat.js` comments) | Retain → done (Phase 8) | 75 rules computed at query time (D17, D31) with the old badge art |
| Old per-day/week/month stat tables + reset jobs | Remove | Replaced by date-range queries |
| Old `payload_games`/`capture_games` (map sets swapped) | Remove | Bug; new app derives mode per match |
| Old frame-count thresholds assuming 30 fps | Remove | Use seconds from timestamps (~20 Hz actual) |
| Heatmap eligibility (Discord link, 5 games/map, 3-day cooldown) | Remove | No accounts; render on demand |
| Home: recent games | Retain | Home page lists latest matches |
| Home: player search | Retain | Name search → player page (D14) |
| Profile stats (full old set, see DataModel) with period switch (day / week / month / all) | Retain | All derivable from match_players; deaths marked estimated |
| Profile: replays list | Retain | Player's match history |
| Profile: "request heatmaps" (per player, per map) | Simplify → Phase 7 | Aggregated on demand from tracks files; no request queue |
| Challenges / "Flamingo Challenges" | Simplify → Phase 8 | Same as achievements (user confirmed); no separate feature |
| Home "Graphs" panel | Retain → Phase 7 | = heatmaps (user confirmed); shown as heatmap tabs |
| Profile "About Me", Login, Discord/Contact links | Remove | No accounts (D5) |
| About Us / collaborators / fun fact text | Simplify | One-line credit to ECRanked in footer |
| echocombat.com frameset, ddns API + websocket | Remove | Offline (D16) |
| Users, Oculus/Discord auth, avatars, moderation | Remove | No accounts (D5) |
| Teams (social groups, join requests) | Remove | Needs accounts |
| Admin / moderation | Simplify → done | One admin password: challenge period + player merges (D33, D34) |
| Matchmaking queue / Bellum | Remove | Out of scope |
| Live capture (APICapture, websockets, active games, reticle, StreamBot) | Remove | Upload-only app |
| Rate limiting | Remove | Local only |
| Legacy `.ecrreplay` import | Defer | Unsafe format (D9) |
