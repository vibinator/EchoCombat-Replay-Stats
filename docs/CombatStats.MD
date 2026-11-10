# Combat stats

Last updated: 2026-11-09. Code: `app/backend/combat.py` (reader), `app/backend/api/combat.py` (endpoints),
`app/frontend/src/components/CombatView.tsx` (player page section), `app/frontend/src/pages/CombatPage.tsx` (`/combat`,
`/combat/:id`). Tests: `tests/backend/test_combat.py`.

**Rule (user, 2026-11-04): the combat stats are completely separate from the replay data.** Own tables, own reader, own
endpoints, own pages/sections. Nothing here reads or writes `replays`, `matches`, `players` or `match_players`, and the
replay-derived stats never use these numbers. Numbers can differ between the two sources, and the site says so.
**Two sources, never merged (user, 2026-11-05, D56):** achievements come from `E:\ECRanked\Replays` or from `E:\ECRanked\matches`. No stat or achievement combines the two. They only share the Achievements page. See "Achievements" below.

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
Player profile: "Combat" tab (only when the player has reports). Replay match page: "Combat" tab for that match (only when
a report exists). Neither is labelled beta (user, 2026-11-05). `/combat` and `/combat/:id` as standalone pages.

## Stats on the site
Game counters: kills, deaths, assists, eliminations, damage, objective eliminations / damage / time, hill captures / defends,
time played. Event-log: shots (and by weapon), kills / deaths by weapon, tac mod activations, heal bubbles, stuns given /
received, self-kills. Derived: K/D, kills per minute, damage per minute, per-map splits, leaderboards. Awards: see below.

## Awards (the game's end-of-match cards, added 2026-11-09)
The recorder decodes the game's `R15NetTopAwardsMsg` (sent once when the scoreboard appears) and writes it into the report as
`awards` (match level: award, stat, value, winner) and `players[].awards` (list of award symbols). Reader: `combat.py`
(`AWARDS`, `_match_awards`, `_player_awards`), stored as JSON in `combat_matches.awards` and `combat_players.awards`
(`COMBAT_VERSION` "2"). **NULL = unknown** (report or events file older than 2026-11-09; the site says "older reports do not
carry the awards"), `[]` = the match handed out none. Only the symbol is stored; names and descriptions live in `AWARDS` so
wording changes need no re-read. An unknown symbol (new award, or a raw `0x...` hash) is kept and shown as written.

**How they are earned (this text is the spec, shown on the site):** there are no thresholds. The game gives **MVP** to the
highest score and up to three more cards, each to the player with the *highest* value of that stat in the match (310 of 317
checks against the replay in the recorder's own test; winners with a value of 1 occur). Which three extra categories appear
is the game's own pick among the stats anyone scored in (looks like a weighted random choice; the lead over second place
makes no difference). A match that ended empty hands out none.

| Symbol | Name | Based on |
|---|---|---|
| `mvp` | MVP | score |
| `assassin` | Assassin | kills |
| `cannoneer` | Cannoneer | damage |
| `super_star` | Super Star | eliminations |
| `hot_shot` | Hot Shot | best elimination streak |
| `sniper` | Sniper | headshot kills |
| `renegade` | Renegade | solo kills |
| `specialist` | Specialist | assists |
| `shock_trooper` | Shock Trooper | stuns |
| `medic` | Medic | healing |
| `tank` | Tank | damage absorbed |
| `guard` | Guard | objective time |
| `defender` | Defender | objective eliminations |
| `controller` | Controller | objective damage |
| `infiltrator` | Infiltrator | hill captures |
| `immovable_object` | Immovable Object | hill defends |

Where it shows: `GET /api/combat/awards` (the guide: key, name, stat, description); player page Combat tab ("Awards" first under
"Combat stats", always shown: the cards won, the ones never won folded under
"Show more", an "Awards" column in Recent combat matches, the guide folded under it); `/combat/:id` and the match page's
Combat tab (the cards as the game showed them: winner, value; badges beside the player names); Leaderboard → Combat: stats
"Awards" and "MVP awards", an "Awards" column, and the guide under the table. Awards are **not** achievements: no medal
uses them yet (one match with award data on 2026-11-09; see "Ideas for later").

## Achievements
The Combat section of the Achievements page (ids 164-178, 198-200 and 202-221 without 211, 212, 216 and 218, `combat_achievements.py`) is built only from `combat_matches` and
`combat_players`, plus `player_aliases` so merged accounts add up. It reuses the medal engine but keeps its own rule list,
`COMBAT_RULES`, which is not in `RULES`, so replay-based overall %, totals, rankings and Medal Collector never include it. The
`/api/players/{id}/achievements`, `/api/achievements` and `/api/achievements/recent` answers add its cards after the replay ones.

A game counts when the report shows the player present for 4+ minutes and 3+ players per team, each there for at least half of the
match. The challenge period applies to the report's start time. A report with no replay counts, and someone with reports but no
replay still gets a page. Results are rebuilt when a report is read, a merge changes or the period changes; only players whose
counted games changed are evaluated again.

Targets are provisional and will be re-tuned as data comes in. All-time targets are estimates. Assists stay above kills at every medal
(user, 2026-11-05; tested).

Calibration data (`E:\ECRanked\matches`, 4 Nov 15:17 to 5 Nov 14:15): 90 matches, 83 of them 4+ minutes, 38 with 3+ players per team,
551 player-games, 264 counted, 140 players, 92 with a counted game. All-time targets are estimates. Assists stay above kills at
every medal (user, 2026-11-05; tested).

Award challenges (user, 2026-11-10, ids 233-264; 222-232, an unreleased "any card" set, stay unused): one per card of the game's end-of-match cards, from `combat_players.awards`. A player wins at most one card per game (checked on 154 matches), so one game = a single medal for the card (249-264, all 16 cards, like Flawless Chassis). One day: MVP (233). Any 7 days: MVP (234), Guard (236), Medic (238). All time: MVP, Guard, Medic, Specialist, Hot Shot (235, 237, 239, 240, 242; 241 Tank and 243 Sniper were dropped, under 10 of 31 regular players win them); the rarer cards (Tank, Sniper, Cannoneer, Controller, Assassin, Renegade, Defender, and Super Star, Shock Trooper, Infiltrator, Immovable Object) are one game only. Targets: the top 10 % of the 31 players with 10+ games with cards (4-9 Nov 2026): all time = their pace x15, any 7 days = their 6 days x7/6, one day = their best day; a day / week page exists only where that crown is 3+. Unknown cards (NULL) count as none. The rare cards are lumpy (Super Star and Immovable Object: 2 winners seen): re-check with more reports.

The month ones (209, 210, 213, 214, 215, 2026-11-10) became any-7-days challenges with the targets x7/30, as every all-time version already existed; the "Month" page is empty and hidden.

Second set (user, 2026-11-09, ids 202-221; 211, 212, 216 and 218 removed the same day as too repetitive, because over 30+ days objective eliminations and objective damage move with kills and damage, 0.98-0.99): one game, one day, any 30 days and all time. The "any 30 days" period (`month`) is new in the
medal engine, a rolling window like "any 7 days" (complete at the window's last game), and so far only Combat uses it; the site shows it
as the "Month" page. Calibration: 435 reports (4-9 Nov 2026), 1451 counted games, 251 players, 42 with 10+ counted games. The crown
is meant to be reachable by about the top 10 % of those 42 (user, 2026-11-09): one game / one day = what the top 10 % reached; any
30 days / all time = the top 10 %'s pace since their first game x30 / x90 (about 3 months, as for gear Veteran; optimistic while the
pace is launch-week). Lower medals keep the ladder's shape. The first set (164-200) is still on its 5 Nov targets, so some of its
all-time crowns (Body Count 1200 kills) sit below the new 30-day ones (Campaign 1600). Heal bubble and stun targets use complete event logs only, as before.

Left out, from the review of the same reports:
- **Eliminations:** always exactly kills + assists (551 of 551 rows), although FORMATS.md calls it a separate counter.
- **Hill captures / defends:** 0 in all 90 reports, Dyson and Combustion included.
- **Event-log numbers:** logging has run since 5 Nov 18:15. Field Medic (heal bubbles) and Shock Trooper (stuns given) use `events_complete` logs only; on 5 Nov that was 9 matches and 30 players, so re-tune them first. Shots are left out on purpose: a shots challenge rewards spraying. Per-weapon challenges can follow once there is more data.
- **Objective fields:** described as payload-only, but Dyson has the most objective time, so they probably cover Capture Point too (reports have no mode field to confirm it).

## API
`GET /api/combat/summary`, `/stats`, `/awards`, `/players/{user_id}` (`period`, `map`; `awards` = counts per card, null when
no match has award data), `/leaderboard` (`stat` incl. `awards` / `mvp`, `period`, `map`, `min_games` default 3, paging),
`/matches`, `/matches/{session_id}` (`awards` cards with winner and value, `players[].awards`). A merged (alias) id answers with its main player and the
aliases' matches are added up (`player_aliases`). Answers are not stamp-cached (the cache stamp follows replays); the
Cloudflare edge cache (`ECHOVR_EDGE_CACHE_S`) still applies.

## Ideas for later (not built)
The data these need is already stored unless noted.
- More award challenges: Tank, Sniper, Defender and the rarer cards were left out in the first set (too few winners); re-check when more weeks of reports carry awards.
- Accuracy-style stats per weapon (kills per 100 shots, shots per death) for matches with events.
- Personal bests and "best match" cards (most kills / damage in one match) with a link to the match.
- Role profile: damage vs objective share, heal bubbles + assists as a support score, stun use.
- Per-weapon leaderboards (kills with Nova, Detonator...), and a "most shots fired" fun board.
- Combat form: K/D and damage per match as a sparkline (like Trends), vs site average.
- Compare page: add the combat numbers side by side.
- Home page: top combat players this week.
- Needs new storage: kill feed / timeline and shot maps from `events\` (times, positions); the report only holds totals.
- Console: combat status (files read, failed, last scan), failed-file list.
