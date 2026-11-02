# Data Model

Last updated: 2026-10-30 — replays come from the read-only share (D25).

## Storage
- SQLite: `data/database/echovr-stats.db` (SQLAlchemy 2.x, WAL mode, foreign keys ON)
- Original files: **not copied**; read in place from the share (`Settings.source_dir`, default `Z:\ECRanked\Replays`, D25). `data/uploads/` is unused.
- Derived files: `data/processed/<replay_id>/tracks.json` (positions, Phase 7)
- Exports: `data/exports/` (temporary)
- IDs are SQLite rowids: a reprocessed match may get the same `id` back.
- Times: `TEXT` ISO-8601 (match times to milliseconds). `discovered_at` / `processed_at` are UTC; `matches.started_at` is the recorder's naive local time (ReplayData Q6).

## Tables

### replays — one per `.echoreplay` file in the share
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| source_path | TEXT UNIQUE NOT NULL | path relative to the share root, `/` separators (e.g. `surge/[2026-10-24 21-31-00] 9EF3….echoreplay`) |
| size_bytes | INTEGER NOT NULL | change → re-queue |
| source_mtime | REAL NOT NULL | file modified time (epoch s); change → re-queue; newest processed first |
| discovered_at | TEXT NOT NULL | UTC |
| container | TEXT NULL | `zip` \| `plain`, set when parsed |
| status | TEXT NOT NULL | `queued` \| `processing` \| `done` \| `failed` |
| error_code | TEXT NULL | `unsupported` (not Combat) \| `corrupt` (bad zip/lines, too big) \| `incomplete` (< 2 frames) \| `unreadable` (I/O error) \| `crashed` (killed the worker twice) \| `internal` (bug; logged) |
| error_message | TEXT NULL | human-readable |
| warnings | TEXT NULL | JSON list (e.g. truncated last line) |
| parser_version | TEXT NULL | set when parsed |
| stats_version | TEXT NULL | set when stats computed |
| processed_at | TEXT NULL | UTC |

Index: `(status, source_mtime)` for newest-first claiming. Files removed from the share keep their rows and match (download → `file_missing`).

### matches — one per successfully parsed replay
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| replay_id | INTEGER UNIQUE FK → replays ON DELETE CASCADE | |
| session_id | TEXT NOT NULL | indexed, not unique (D13) |
| map_code | TEXT NOT NULL | e.g. `mpl_combat_gauss` |
| map | TEXT NOT NULL | `combustion` \| `dyson` \| `fission` \| `surge` \| `unknown` |
| mode | TEXT NOT NULL | `capture_point` \| `payload`, fixed per map (D26); unknown map → from fields present |
| private_match | INTEGER NOT NULL | bool |
| tournament_match | INTEGER NOT NULL | bool |
| recorded_by | TEXT NULL | `client_name` |
| started_at | TEXT NOT NULL | first frame timestamp |
| ended_at | TEXT NOT NULL | last frame timestamp |
| duration_s | REAL NOT NULL | |
| frame_count | INTEGER NOT NULL | |
| frame_rate_hz | REAL NOT NULL | frame_count / duration |
| blue_rounds | INTEGER NOT NULL | final `blue_round_score` |
| orange_rounds | INTEGER NOT NULL | final `orange_round_score` |
| final_blue_points | REAL NULL | capture-point only |
| final_orange_points | REAL NULL | capture-point only |
| final_payload_checkpoint | INTEGER NULL | payload only |
| final_payload_distance | REAL NULL | payload only |
| contested_s | REAL NOT NULL | time `contested` = true |
| has_tracks | INTEGER NOT NULL | bool; position tracks file saved (Import page counts these instead of checking files) |
| blue_capture_s / orange_capture_s | REAL NOT NULL | capture point: time that team's progress was rising (0 when not recorded) |
| winner | TEXT NULL | `blue` \| `orange` \| NULL. Capture point: more rounds. Payload: attacking team if final checkpoint = 3, defending team if timer = 0, else NULL |
| attacking_team | TEXT NULL | payload only (ReplayData Payload semantics) |
| final_game_timer | REAL NULL | payload only; seconds left |

### players — one per `userid`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| user_id | TEXT UNIQUE NOT NULL | platform userid as string (D8) |
| name | TEXT NOT NULL | latest name seen |
| first_seen_at | TEXT NOT NULL | match started_at |
| last_seen_at | TEXT NOT NULL | match started_at |

### match_players — per player per match (stats, D10)
| Column | Type | Notes |
|---|---|---|
| match_id | INTEGER FK → matches ON DELETE CASCADE | PK part |
| player_id | INTEGER FK → players | PK part |
| team | TEXT NOT NULL | `blue` \| `orange` (team of most frames) |
| name | TEXT NOT NULL | name in this match |
| slot | INTEGER | `playerid` |
| number | INTEGER | |
| level | INTEGER | |
| first_frame | INTEGER NOT NULL | |
| last_frame | INTEGER NOT NULL | |
| frames_present | INTEGER NOT NULL | |
| play_time_s | REAL NOT NULL | |
| left_early | INTEGER NOT NULL | bool; last seen > 45 s before end (old "crashed") |
| ping_sum | REAL NOT NULL | sum of real readings (ping 999 excluded, D24) |
| ping_frames | INTEGER NOT NULL | frames with a real reading; avg ping = ping_sum ÷ ping_frames |
| frames_in_bounds | INTEGER NOT NULL | denominator for below |
| speed_sum | REAL NOT NULL | ÷ frames_in_bounds = avg speed |
| top_speed | REAL NOT NULL | highest speed held for a full 1 s (max of rolling 1 s min, in-bounds samples; window resets on death) |
| frames_stopped | INTEGER NOT NULL | speed < 1 m/s |
| frames_upside_down | INTEGER NOT NULL | body.up.y < 0 |
| frames_near_mate | INTEGER NOT NULL | dist² < 7 |
| frames_near_enemy | INTEGER NOT NULL | dist² < 7 |
| frames_left_arm | INTEGER NOT NULL | |
| frames_right_arm | INTEGER NOT NULL | |
| deaths_est | INTEGER NOT NULL | out-of-bounds heuristic (estimated) |
| payload_push_s | REAL NOT NULL | estimated; within 3 m of payload while attackers counted, attacking team only |
| packet_loss_sum | REAL NOT NULL | ÷ frames_present = avg packet loss ratio |
| emote_count | INTEGER NOT NULL | emotes started (`is_emote_playing` false → true) |
| payload_block_s | REAL NOT NULL | estimated; within 3 m while defenders counted, defending team only |

### match_player_loadouts — loadout usage
| Column | Type | Notes |
|---|---|---|
| match_id | INTEGER FK → matches ON DELETE CASCADE | PK part |
| player_id | INTEGER FK → players | PK part |
| weapon | TEXT NOT NULL | PK part; `""` allowed |
| tacmod | TEXT NOT NULL | PK part |
| ordnance | TEXT NOT NULL | PK part |
| frames | INTEGER NOT NULL | in-bounds frames using this combo |

### events — timeline
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| match_id | INTEGER FK → matches ON DELETE CASCADE | |
| frame | INTEGER NOT NULL | |
| t_s | REAL NOT NULL | seconds since match start |
| type | TEXT NOT NULL | see below |
| player_id | INTEGER NULL FK → players | |
| team | TEXT NULL | |
| data | TEXT NULL | JSON |

Event types (v1): `player_join` / `player_leave` (only mid-match: not at frame 0 / not in last frame), `loadout_change` (also the first loadout; data: weapon, tacmod, ordnance), `respawn` (out → in bounds), `death_est`, `respawn`, `loadout_change`, `death_est` (data: x, z of last in-bounds head position), `round_won` (data: blue/orange rounds), `payload_checkpoint` (data: checkpoint, time_left_s before the +120 s bonus), `contest_start`, `contest_end`.

### duplicate_matches — copies of a match recorded twice (D13)
| Column | Type | Notes |
|---|---|---|
| match_id | INTEGER PK FK → matches ON DELETE CASCADE | this copy does not count towards stats |
| counted_match_id | INTEGER FK → matches ON DELETE CASCADE, index | the copy that counts (same session, overlapping time) |

Derived like the tables above: recomputed for a session whenever one of its matches is saved or deleted, and for
the whole archive at startup (`duplicates.refresh_all`, ~0.05 s). Stat queries leave these rows out with
`duplicates.counted(<match id column>)`.

## Derived (computed in API, not stored)
| Stat | Formula |
|---|---|
| avg_ping | ping_sum / ping_frames |
| avg_speed | speed_sum / frames_in_bounds |
| pct_stopped / pct_upside_down / pct_near_mate / pct_near_enemy | frames_x / frames_in_bounds |
| dominant_arm | larger of frames_left_arm / frames_right_arm |
| Player aggregates | SUM of counts / SUM of denominators across match_players (filtered by map, date range) |

### Player profile set (old site parity)
| Stat | Formula |
|---|---|
| total_games; games per map; capture_point_games / payload_games | COUNT(match_players), grouped by `matches.map` / `matches.mode` |
| total_deaths_est; deaths_per_game_est | SUM(deaths_est); ÷ total_games |
| avg_speed; top_speed | SUM(speed_sum) / SUM(frames_in_bounds); MAX(top_speed) |
| avg_ping | SUM(ping_sum) / SUM(ping_frames) |
| pct_idle / pct_inverted / pct_near_mate / pct_near_enemy | SUM(frames_x) / SUM(frames_in_bounds) |
| pct_left_arm / pct_right_arm | SUM(frames_*_arm) / SUM(frames_in_bounds) |
| pct_left_early | SUM(left_early) / total_games (old "percent crash") |
| level | match_players.level from latest match |
| wins / losses | matches with `winner` = / ≠ the player's team; matches with unknown winner count for neither |
| hours_played | SUM(play_time_s) / 3600 |
| loadout usage; top loadout | SUM(frames) per combo from match_player_loadouts |

Every profile stat takes a period: day / week / month / all (calendar, recorder local time).

Profile also: avg_packet_loss = SUM(packet_loss_sum) / SUM(frames_present); emote_count = SUM(emote_count).

Leaderboard = the same aggregates grouped by player, ranked in Python by the chosen stat (lower-is-better: ping, deaths/game, idle), players with < `min_games` excluded; optional `private_match` filter (old app had none). Loadout stat = SUM(frames / matches.frame_rate_hz) / 3600 for matching weapon/ordnance/tacmod.

### Achievements (Phase 8, D17, D31, D52)
No table: computed from `match_players` + loadouts + `matches` on request (`backend/achievements.py`). 122 rules (ids 5-126). Almost all are medal ladders (D52): `levels` = targets for bronze, silver, gold, diamond, platinum; `count` is evaluated per period group (game / day / week / all time) and the best group counts; progress = 20 % per medal. Single-step rules (Pew Pew Proof, gear sets) keep white 25 / bronze 50 / silver 75 / gold 100 %. Overall = mean progress; Medal Collector (id 126) counts gold-or-better medals of the others. Leaderboard `stat=achievements` ranks overall % (all time).

## Kept across rebuilds (not derived from the share)
| Table | Columns | Purpose |
|---|---|---|
| app_settings | key PK, value, updated_at | Admin settings: `challenge_start`, `challenge_end` (D33) |
| player_aliases | alias_user_id PK, main_user_id (index), created_at | Player merges, applied in `save_match` (D34) |
| repair_requests | source_path PK, requested_at | Replays processed in repair mode (D36) |
| aggressive_repairs | source_path PK, requested_at | Replays processed in aggressive repair mode (D36b) |

## Tracks file (Phase 7, D11, D30)
`data/processed/<replay_id>/tracks.bin` = zlib( uint32 header length | header JSON | arrays ), little-endian.
- Header: `{version: 1, hz: 2, samples, weapons: [codes], players: [user_id…], series: {blue_points?, orange_points?, payload_distance?: [value|null per sample]}}`.
- Per player, in header order: `x` int16[samples], `z` int16[samples] (decimetres), `weapon` uint8 (index into `weapons`, 255 = none), `team` uint8 (0 absent, 1 blue, 2 orange); version 2 adds `tacmod`, `ordnance` uint8 (indexes into `tacmods` / `ordnances`). Version-1 files read with no tac mod / ordnance.
- First frame of each 0.5 s slot; written by the worker while processing; ≈ 9–26 KB per match (≈ 0.6 GB for the archive). Overwritten on reprocess; rebuildable.

## 3D tracks file (3D playback, docs/WebReplayer-Review.MD Phase 2)
`data/processed/<replay_id>/tracks3d.bin` = zlib( uint32 header length | header JSON | arrays ), little-endian (`app/backend/tracks3d.py`).
- Header: `{version: 1, hz: 5, samples, players: [user_id…], payload?: [[x, y, z] metres | null per sample]}`.
- Per player, in header order: `x`, `y`, `z` int16[samples] (head position, decimetres), `yaw` uint8 (256 steps, 0 = facing +z, 64 = +x), `pitch` int8 (degrees, + = up), `team` uint8 (0 absent, 1 blue, 2 orange).
- First frame of each 0.2 s slot, from the same pass as `tracks.bin`; load-in spot samples absent. ≈ 16–118 KB per match (about 4× `tracks.bin`). Overwritten on reprocess; rebuildable.

## Heatmap cache (D18)
In memory (`functools.lru_cache`, 64 entries) keyed by player, map, mode, period, last N and a data stamp (done count + latest `processed_at`), so any import change recomputes. Not persisted; cold requests read the player's tracks files (≈ 1–3 s for 200 matches).

## Indexes
- replays.sha256 UNIQUE; replays.status
- matches.session_id; matches.started_at; matches.map; matches(private_match, started_at)
- players.user_id UNIQUE; players.name
- match_players(player_id); match_players(player_id, match_id): covering for per-player counts without duplicates (D13);
  match_players.top_speed (home "fastest player", D50)
- match_player_loadouts(weapon, ordnance, tacmod, match_id, frames): covering, home "most popular gear" (D50)
- events(match_id, t_s)

## Reprocessing
- The database is a cache of the share (D25): no migrations. On startup, a column mismatch in a derived table (matches, match_players, loadouts, events) drops those tables and clears `stats_version` (matches rebuilt); a mismatch in `replays`/`players` drops every table (the scanner re-imports all files, ≈ 3 h) — a last-resort fallback only: future changes to those tables come with a migration (D27).
- Reprocess (API, file change or version change): deletes the match row (cascades) and re-runs the pipeline from the original. `players` rows are kept.

## Retention
- Originals live only in the share and are never modified, moved or deleted by the app (D25).
- No delete in the app. Deleting the database file rebuilds everything from the share.
