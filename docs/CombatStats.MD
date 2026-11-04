# Combat stats

Last updated: 2026-11-04. Code: `app/backend/combat.py` (reader), `app/backend/api/combat.py` (endpoints),
`app/frontend/src/components/CombatView.tsx` (player page section), `app/frontend/src/pages/CombatPage.tsx` (`/combat`,
`/combat/:id`). Tests: `tests/backend/test_combat.py`.

**Rule (user, 2026-11-04): the combat stats are completely separate from the replay data.** Own tables, own reader, own
endpoints, own pages/sections. Nothing here reads or writes `replays`, `matches`, `players` or `match_players`, and the
replay-derived stats never use these numbers. Numbers can differ between the two sources, and the site says so.

## Where the data comes from
The ECRanked recorder PC writes plain JSON next to the replays (`E:\ECRanked`, shown as `Z:\ECRanked` on the PC that runs
the site). Its own format documentation is `reference\formats\FORMATS.md` and the `*.schema.json` files there.

| Folder | Content | Used here |
|---|---|---|
| `matches\<MatchID>.json` | One report per finished match: every non-spectator player with the game's counters and, when the match has an event log, the event totals | **Yes, the only input** |
| `events\<MatchID>.json` | Every decoded event (shot, kill, tac mod on/off, heal bubble, stun) with positions and times | No (its totals are already inside the report) |
| `combat_stats\<MatchID>\<name>.json` | The same game counters as increments, per player | No (repeats the report) |
| `Replays\`, `eventlogs\`, `reference\`, `discoveries\` | Replays, raw network logs, lookup tables | No |

## How it is collected (same way as the replays)
1. The recorder folder is mounted read-only next to the replay share (`ECHOVR_COMBAT_SOURCE`; default = the replay folder itself if it contains `matches\`, else the folder above it). On the QNAP NAS the recorder folder is `/share/ECRanked/ECRanked`, already mounted at `/replays`, so `docker-compose.yml` sets `ECHOVR_COMBAT_SOURCE: /replays`.
2. `CombatIngest` (thread) stats the `matches` folder every `ECHOVR_COMBAT_SCAN_S` (60) and lists it when its modified time
   changed, a file is still settling, or every 5 min.
3. A file written in the last `settle_s` (120 s) waits. A new file, or one whose size / modified time / `COMBAT_VERSION`
   changed, is read and saved in one transaction (`combat_files` row = the queue/status, like `replays`). Newest first.
4. A bad file is stored as `failed` with the reason and retried only when it changes; it never stops the others.
5. Reports are a few KB and complete, so there is no process pool.

Raise `COMBAT_VERSION` in `combat.py` when the reader keeps more or different data: every report is read again.

## Tables
`combat_files` (path, size, mtime, status, error, version), `combat_matches` (session id, map, start/end, duration,
`has_events`, `events_complete`, team totals JSON), `combat_players` (one row per account per match: the counters, the
event numbers, per-weapon JSON, loadouts JSON). They are a cache of the folder and can be rebuilt from it. They are
listed in `db.COMBAT_TABLES`: a column change drops and re-reads only these, never the replay tables.

## Rules for the numbers (from FORMATS.md)
- **Ids are text.** `userid` is 64-bit; keep it a string everywhere. Join players on `userid`, never on name.
- **`events` null = unknown, not 0.** Event numbers are stored NULL when the match had no event log, and only matches with
  one are counted in event totals (the page says "N of M matches have an event log").
- **`events_complete = false`** means the log ended early: shots / weapon counts of that match are too low. Shown as a note.
- **Damage taken is never shown.** Spectators do not get it; the files always hold 0.
- **kills** exclude self-kills, **deaths** include them (`self_kills` counts the difference). **eliminations** is the game's
  separate, usually larger counter.
- Times have no time zone (the recording PC's clock), the same clock as replay matches, so the Today / Week / Month filters match.
- Weapon names: the game's lower-case symbols mapped to in-game names (`assault` Pulsar, `r15_ord_det` Detonator,
  `scout_aoe` Comet blast...). Unknown symbols stay as written, raw `0x...` hashes unchanged.
- `weapon_value` in shot events is unconfirmed by the recorder's docs: not used.

## Where it shows
Player profile: "Beta Data Collection" section (still beta). Replay match page, Players tab, right under the players:
"Combat stats" for that match (not beta, only when a report exists). `/combat` and `/combat/:id` as standalone pages.

## Stats on the site
Game counters: kills, deaths, assists, eliminations, damage, objective eliminations / damage / time, hill captures / defends,
time played. Event-log: shots (and by weapon), kills / deaths by weapon, tac mod activations, heal bubbles, stuns given /
received, self-kills. Derived: K/D, kills per minute, damage per minute, per-map splits, leaderboards.

## API
`GET /api/combat/summary`, `/stats`, `/players/{user_id}` (`period`, `map`), `/leaderboard` (`stat`, `period`, `map`,
`min_games` default 3, paging), `/matches`, `/matches/{session_id}`. A merged (alias) id answers with its main player and the
aliases' matches are added up (`player_aliases`). Answers are not stamp-cached (the cache stamp follows replays); the
Cloudflare edge cache (`ECHOVR_EDGE_CACHE_S`) still applies.

## Ideas for later (not built)
The data these need is already stored unless noted.
- Accuracy-style stats per weapon (kills per 100 shots, shots per death) for matches with events.
- Personal bests and "best match" cards (most kills / damage in one match) with a link to the match.
- Role profile: damage vs objective share, heal bubbles + assists as a support score, stun use.
- Per-weapon leaderboards (kills with Nova, Detonator...), and a "most shots fired" fun board.
- Combat form: K/D and damage per match as a sparkline (like Trends), vs site average.
- Compare page: add the combat numbers side by side.
- Home page: top combat players this week.
- Needs new storage: kill feed / timeline and shot maps from `events\` (times, positions); the report only holds totals.
- Console: combat status (files read, failed, last scan), failed-file list.
