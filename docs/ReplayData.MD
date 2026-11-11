# Replay Data

Last updated: 2026-10-29

Legend: **C** = confirmed (read directly from reference code / sample files), **A** = assumption, **U** = unknown.

Sources inspected (read-only): `ECRanked/Replays/{combustion,dyson,fission,surge}` (first 12 zipped samples; on 2026-10-29 replaced by 4 plain-text files of the same matches 5D75EBD9, 5F6027A3, 9BF839F5, 9EF3682D — full field survey of those 4 done; plus 2 larger plain files added 2026-10-30: fission BEB8E023 (99 MB, 500 s), surge CCFFD14B (116 MB, 591 s)), 4 in `other scripts/ECRanked/*/`, plus `ECRanked/skims.py`, `ConvertToEchoReplay.py`, `htdocs/prisma/schema.prisma`, `htdocs/src/routes/*`.

## File format
| Item | Status | Notes |
|---|---|---|
| Extension | C | `.echoreplay` (legacy ECRanked `.ecrreplay` = bz2 pickle, see Legacy) |
| Container | C | Two variants: **(a)** ZIP (deflate) containing `<sessionid>.echoreplay`; **(b)** the same text stored uncompressed (no zip). Detect by magic `PK\x03\x04`. |
| Extra zip entries | C | Recorded zips also contain `images/image.png`, which in samples is a byte-for-byte copy of the frame text (same size, starts with a timestamp). Ignore all entries except the first `*.echoreplay`. |
| Record layout | C | One frame per line: `<timestamp>\t<JSON object>\n` |
| Timestamp format | C | `YYYY-MM-DD HH:MM:SS.ffffff` in recordings; `YYYY/MM/DD HH:MM:SS.fff` in files written by old converter. Accept both. |
| Timestamp timezone | U | Local time of the recording PC, no offset stored. Old app assumed Europe/London. Store naive + treat as local. |
| Header / version | C | None. No version field; frame JSON is the Echo VR local HTTP API (`/session`) response. Format detected by structure. |
| Sample rate | C | Usually 18.9–19.8 Hz; one plain-text sample (10 players, 84 s) is 14.6 Hz. Not fixed; use timestamps, never frame index × constant. |
| Size | C | 2–9 MB zipped, 13–116 MB uncompressed for 3–12 min matches. Parse + stats ≈ 3 s for 116 MB. |
| Integrity | C | No malformed lines and no gaps > 1 s in any of 12 samples. Parser must still tolerate a truncated last line. |

## Archive formats by date (C: per-quarter sample of the share, 2026-10-30)
| Period | Loadout + Arm | payload / timers / contested / points | Timestamp |
|---|---|---|---|
| ≤ 2021 Q3 | absent | absent | `YYYY/MM/DD …fff` (old converter) |
| 2021 Q4 – 2022 Q3 | present | absent | `YYYY-MM-DD …ffffff` |
| ≥ 2022 Q4 | present | present | `YYYY-MM-DD …ffffff` |
- Share (`Z:\ECRanked\Replays\{combustion,dyson,fission,surge}`): 29,439 `.echoreplay` (all zipped in samples), 2021-09 → 2026-10; per year 2021: 3,309 · 2022: 12,656 · 2023: 4,999 · 2024: 2,249 · 2025: 3,828 · 2026: 2,398.
- Consequences: mode must come from the map (D26); payload winner/attacking team/push-block unknown before 2022 Q4; loadout and arm stats empty before 2021 Q4 (frames without loadout are not counted as a loadout). 24 / 24 sampled files (4 per year) parse.

## Decoding approach
1. Read first 4 bytes → zip or plain text.
2. Zip: open first entry ending `.echoreplay`; stream lines (do not load 75 MB at once).
3. Split each line on the first `\t`; parse timestamp; `json.loads` the rest.
4. Skip blank lines. Unparsable **last** line → warning only (truncated recording). Unparsable lines elsewhere → warning with count; `corrupt` once they exceed max(10, 1 % of lines read).
5. First non-blank line unreadable → `corrupt`. No frames → `incomplete`; fewer than 2 readable frames → `incomplete` (no duration).
6. Reject if `match_type != "Echo_Combat"` → `unsupported` (all samples are Combat; Arena has a different schema).
7. Zip: damaged/truncated zip, no `.echoreplay` entry, or content > 1 GB uncompressed → `corrupt`.
- C (parser v1, 2026-10-29): all 16 samples parse with no warnings, 0.3–1.9 s each (1,225–14,302 frames). Hand poses, `is_emote_playing`, `packetlossratio` beyond storage, and `player`/`last_throw` blocks are not read (unused by any planned stat).

## Available fields
### Frame (top level)
| Field | Status | Reliability | Notes |
|---|---|---|---|
| sessionid | C | High | GUID, constant per match; same match recorded twice shares it |
| sessionip | C | High | Server IP — do not display (privacy) |
| match_type | C | High | `Echo_Combat` in all samples |
| map_name | C | High | `mpl_combat_combustion`, `mpl_combat_dyson`, `mpl_combat_fission`, `mpl_combat_gauss` (= Surge) |
| private_match, tournament_match | C | High | bool |
| client_name | C | High | Name of the recording client (often a spectator) |
| blue_round_score, orange_round_score | C | High | Rounds won; only change on capture-point maps |
| total_round_count | C | Medium | Always 0 in samples |
| contested | C | High | Point/payload contested flag |
| blue_points, orange_points | C | High | **Capture-point maps only** (Combustion, Dyson): capture progress 0–100 |
| payload {pos, checkpoint, distance, speed, attackers, defenders, multiplier} | C | High | **Payload maps only** (Fission, Surge). Never used by the old app. See Payload semantics |
| timers {game_timer, overtime_timer} | C | High | **Payload maps only**. game_timer holds 180 until the payload first moves, then counts down; +120 s per checkpoint reached (max seen 329). **Overtime**: when game_timer hits 0 while contested, overtime_timer counts down from 4 s (seen once; it ran out → defence win) |
| pause {paused_state, ...} | C | High | Always `none` in samples |
| teams[3] | C | High | Index 0 blue, 1 orange, 2 spectators; `players` key absent when team empty. **`team` label can be a custom name** (seen for orange) → always use the index |
| player {vr_*} | C | — | Recording client's own camera; not useful |
| last_throw, *_shoulder_pressed*, err_code | C | — | Arena leftovers / client input; ignore |

### Player (inside `teams[i].players[]`)
| Field | Status | Reliability | Notes |
|---|---|---|---|
| userid | C | High | Platform user ID, up to 19 digits (**> 2^53**) but also 3–5-digit IDs seen → store/serve as string |
| name | C | High | Display name (can change between matches) |
| playerid | C | High | Slot index within the match (0–9), not a global ID |
| number, level | C | High | Jersey number, account level |
| ping, packetlossratio | C | High | Per frame. **ping = 999** appears mid-match (≤ 7.4 % of a player's frames; A: no-reading placeholder); old app averaged it in, **new app excludes it** (D24). packetlossratio up to 0.12 |
| head/body {position, forward, left, up}; lhand/rhand {pos, forward, left, up} | C | High | Metres, Y up |
| velocity | C | High | m/s vector |
| Weapon | C | High | `assault, blaster, rocket, scout, rifle, smg, chain, magnum`; `""` is common (up to 37 % of player-frames) |
| TacMod | C | High | `heal, sensor, shield, wraith, buff`; may be `""` |
| Ordnance | C | High | `det, stun, arc, burst, loc, dot, drone`; may be `""` |
| New codes (2026-10) | C | — | `drone` (ordnance), `buff` (tac mod) seen in the Oct-2026 files; names in Loadout names |
| Ability / Grenade | C (old code) | — | Older API names for TacMod / Ordnance; parser v2 falls back to them |
| Arm | C | High | `Left` / `Right` (dominant arm) |
| is_emote_playing | C | High | bool |
| Kills / deaths / damage / health / stuns | C (absent) | — | **Not in the API.** No per-player combat stats exist. |
| Shots fired / ordnance thrown / tac mod used | C (absent, checked 2026-10-31 on a 2026-10-31 file) | — | **Not in the API.** No trigger, ammo, cooldown or ability-use field per player; `Weapon` / `TacMod` / `Ordnance` only say what is equipped. Top-level `last_throw` and `*_shoulder_pressed*` are the recording client's own Arena leftovers, not players. So shot / use counts per gear cannot be computed. |

### Payload semantics (C from 2 plain + 3 other payload samples; meaning of counts is A)
| Field | Observed |
|---|---|
| attackers / defenders | Number of attacking / defending players on the payload (0–4 / 0–2 seen) |
| contested | True exactly when attackers > 0 and defenders > 0 |
| multiplier | = attackers when uncontested; 0 when contested or empty; −1 = rolling back (speed < 0) |
| speed | m/s along the track, −0.47 to 2.55 |
| checkpoint | 0 → 3; 3 = track end (distance ≈ 181.81 fission, ≈ 206.80 surge) |
| On payload | Head within **3 m** of `payload.pos` (C: best match to the API counts — 92 % attackers, 99 % defenders; 6 m only 81 % / 90 %) |
| Attacking team | Team with most player-frames on the payload while attackers > 0 and defenders = 0 (A; orange in all 4 decided samples) |
| End of match | Track end reached with timer > 0 (attack win), or game_timer = 0 at checkpoint < 3 (defence win); else recording stopped early |

### Fields never used by the old app (all C, documented above)
`payload.*`, `timers`, `contested`, `blue_points`/`orange_points`, `lhand`/`rhand`, `head.forward/up`, `body.position/forward`, `is_emote_playing` (≈1 % of player frames), `packetlossratio` (0–0.03), newer loadout codes (frequency in 4 samples: rifle 13 %, smg 4 %, chain/magnum < 0.1 %; loc 7 %, dot < 0.1 %). Always constant in samples (ignore): `last_throw.*`, `*_shoulder_pressed*`, `pause.*` (none), `err_code`, `total_round_count`, `private_match`/`tournament_match` (all false).

## Raw data → statistics mapping
| Statistic | Source fields | Status |
|---|---|---|
| Map, mode, date, duration, frame rate | map_name, timestamps | C |
| Teams / players | teams[0..1].players[].userid/name | C |
| Result (capture-point maps) | final blue/orange_round_score | C |
| Result (payload maps) | payload.checkpoint, game_timer + attacking team | A — rule in Payload semantics; implemented (stats v3). Samples: 3 attack wins, 1 defence win, 2 unknown (payload never moved) |
| Push / block time per player | head within 3 m of payload while API counts attackers / defenders | A (estimated) |
| Capture progress timeline | blue_points / orange_points per frame | C |
| Payload progress timeline | payload.distance / checkpoint per frame | C |
| Contested time | contested | C |
| Play time per player | frames present × Δt | C |
| Crashed / left early | last frame seen < end − 45 s (old rule) | C (heuristic) |
| Deaths | in-bounds → out-of-bounds transition of head position, per-map bounds (old rule) | A — heuristic, unvalidated |
| Avg/top speed | ‖velocity‖; top = max of 1 s rolling minimum (old rule) | C |
| % stopped | speed < 1 m/s | C |
| % upside down | body.up.y < 0 | C |
| % near teammate / enemy | head distance² < 7 (≈2.65 m) | C |
| Avg ping | ping | C |
| Pub vs private match | private_match | C field; old app never filtered on it ("pub" counts = all games) |
| Dominant arm | Arm | C |
| Loadout usage | Weapon + TacMod + Ordnance per frame | C |
| Positions (timeline / heatmap) | head.position per frame | C |
| Goals / assists / saves / steals / interceptions | — | Not derivable (Arena concepts) |
| Kills / damage / stuns | — | Not derivable |
| Possession | — | Not applicable (no disc in Combat); replaced by contested / payload control |

## Loadout names (C: user-supplied gear table, `docs/reference/gear-table.json`; code: `app/backend/gear.py`)
API values may be text codes or older hex symbols (`0x…`, see below). `cut` = never released, yet present in Oct-2026 replays.
| Slot | Released | Cut / unreleased |
|---|---|---|
| Weapon | assault Pulsar, blaster Nova, scout Comet, rocket Meteor | magnum Protostar, smg Quark, chain Blazar, rifle Starburst |
| Ordnance | det Detonator, stun Stun Field, arc Arc Mine, burst Instant Repair | loc Translocator, dot Dot Field, drone Attack Drone |
| TacMod | heal Repair Matrix, sensor Threat Scanner, shield Energy Barrier, wraith Phase Shift | buff Overcharge, smoke Umbral Veil, point Neutron |
- `""` (empty) → shown as "None". Unknown codes → shown as the raw code.
- `smoke`, `point` not yet seen in any sample. Weapon `aliases` (e.g. `scout rifle explosion`, `blaster_cone`, `rocket_aoe`) look like damage-source names; **no such field exists in any sample** (no kill/damage data).
- Old 64-bucket loadout encoding only covers 4×4×4; newer codes can't be represented → confirms storing names (Decisions).
- Hex symbols: Pulsar `0x2FD69C8C5F615B9E`, Nova `0x2FD5839E4D605298`, Comet `0xE32DC7C9DA8051A4`, Meteor `0x41D2D5321928020A`, Detonator `0xC8E8D0B1A894E7FE`, Stun `0xC8C33E4829670BBE`, Arc `0xC8E8D0B1A891F0E9`, Instant Repair `0xE32DC7D8CC9D57A4`, Repair Matrix `0xC8C33E4832761FBC`, Threat Scanner `0x41D2D4381430080C`, Barrier `0x41D2D43513260B1A`, Phase Shift `0x41D2D02F1B2A1316`. U: which replay versions emit them (A: older API).

## Map bounds (old app, used for deaths and in-bounds stats)
- C (old `skims.py`): ping counts every frame; speed, stopped, upside down, arm, loadout and near mate/enemy count **in-bounds frames only**; near = any other player's head (wherever it is) within dist² < 7; death = player's previous frame in bounds and current frame out of bounds.
- **Round ends (2026-11-11, user, STATS_VERSION 15):** 18.5-18.9 s after a round that does not decide a capture-point match, everybody on the map is moved to the war room; a death 17.5-20.5 s after such a round (`stats/__init__.py` ROUND_MOVE_S) is that move and is not counted.
- **Spawn points (2026-11-10, user, STATS_VERSION 13):** circles (x, z, radius), `stats/maps.py` SPAWN_CIRCLES; since 2026-11-11 (STATS_VERSION 14) the measured arrival spots, 1.5 m each (bounds editor, `make.py` measure_spawns), and dyson's bounds reach x ±110 for its two entry tubes. An in → out-of-bounds step whose last in-bounds position is inside one is a walk back to the war room, not a death.
- **Corrected 2026-11-10 (user, STATS_VERSION 12):** combustion, fission and surge had x and z swapped; they are now x -20..60 / z -100..100, x -80..130 / z -30..40 and x -60..150 / z -50..70 (dyson unchanged: x -100..100 / z -40..40). Found through the home page's Deaths heatmap: a straight line of "deaths" along z = -20 on Combustion. Still boxes: the user is to draw the real outlines (bounds editor). What follows is the history.
- Kept as-is by user decision (Decisions D20) until then. **C (2026-10-29, 16 samples): these bounds look wrong for combustion, fission and surge** (x/z swapped vs the minimap/heatmap extents). Share of head positions inside: fission 24 % (old) vs 72 % (heatmap extent), surge 51 % vs 73 %, combustion 62 % vs 75 %, dyson 79 % vs 78 %. Out-of-play positions sit far away (|x|, |z| ≈ 150–200: spawn/respawn areas). Deaths change by up to ±7 per match.
| Map | x min | x max | z min | z max |
|---|---|---|---|---|
| dyson | -100 | 100 | -40 | 40 |
| combustion | -100 | 100 | -20 | 60 |
| surge | -50 | 70 | -60 | 150 |
| fission | -30 | 40 | -80 | 130 |

### Heatmap image extents (C, old `other scripts/HeatMap.py`)
Separate from the bounds above; used only to size heatmap images. Axes: x = `position[0]`, z = `position[2]`; image row flipped (z up).
| Map | x min | x max | z min | z max |
|---|---|---|---|---|
| dyson | -54.625 | 54.625 | -41.125 | 28.375 |
| combustion | -18.25 | 55.625 | -87.625 | 86.625 |
| surge | -55.625 | 149.5 | -47 | 62.625 |
| fission | -74.125 | 124.5 | -23.125 | 34.125 |
- Minimaps (C, copied from old `htdocs/public/` to `docs/reference/minimaps/`): high-res and low-res PNG per map, transparent background.
| Map | High-res px | Aspect | Extent aspect (Δx/Δz) | Fit |
|---|---|---|---|---|
| dyson | 2731×1738 | 1.571 | 1.572 | width = x |
| combustion | 4357×1845 | 2.362 | 0.424 (Δz/Δx 2.359) | **rotated 90°**: width = z |
| surge | 3320×1774 | 1.871 | 1.871 | width = x |
| fission | 5049×1454 | 3.472 | 3.469 | width = x |
- C (2026-10-30, plotted sample head positions over the low-res images): each minimap spans the heatmap extent. Layout: dyson / fission — x left→right, z bottom→top; surge — x left→right, z **top→bottom**; combustion — **rotated**: z left→right, x top→bottom. High-res images (2026-10-30, D35): chosen orientation by share of positions on opaque pixels + team spawn side — dyson as-is, combustion mirrored, fission and surge **flipped vertically** (99–100 % on the map; team colours match the side each team starts on). The **low-res dyson image has blue/orange swapped** (geometry fine). App uses the corrected high-res images (`app/frontend/public/minimaps/`) and thumbnails made from them.
- U: why the extents differ from the in-bounds table (e.g. combustion x range).
- Positions plotted: `head.position` only, in-bounds samples only.
- Death location (old heatmap): last in-bounds head position before an in→out-of-bounds transition (same heuristic as deaths).

## Not derivable
- Kills, damage, health, stuns, assists — not in the API.
- Arena stats (goals, saves, possession) — wrong game mode.
- Kills/damage remain absent in the newest data (full survey, 2026-10-29).

## Verification against the old app (C, 2026-10-29)
Old `skims.py` `CaculateSkims` run read-only on the 4 plain samples (16 players): frames, ping, in-bounds frames, avg speed, stopped, upside down, near mate/enemy, deaths, arm and crashed/left-early **match exactly**. Top speed matches in 14 / 16; differs in 2 (≤ 0.29 m/s) because the new rule needs a full 1 s window and resets on death (old: frame-count buffer kept across deaths).

## Repair (salvage) mode (D36)
- Damaged zip: inflate the first `.echoreplay` entry straight from its local header (central directory and CRC ignored) until the data ends or breaks; everything before the damage is kept.
- Unreadable lines, including the first, are skipped without limit; still needs ≥ 2 readable frames and `Echo_Combat`.
- Check (2026-10-30): a real zipped replay cut to 60 % → normal parse `corrupt`; repair recovered 3,764 frames (190 s of play).

## Aggressive repair (D36b)
- What the 80 replays still failing after repair (2026-11-02) look like: 60 empty or all zero bytes (nothing to recover); 20 with 4 KB disk blocks overwritten by zeros or by another file's data, local zip headers wiped, sometimes another match's entries in the central directory.
- Recorded zips hold the frames twice with identical compressed bytes (`.echoreplay` and `images/image.png`): damage in one copy is patched from the other.
- zlib decodes zeros / foreign data without an error into junk, so each decoded line must parse as a frame; reading stops at the first one that does not. Nothing after a gap in both copies is recoverable (back-references into the lost window).
- Check (2026-11-02): 12 of the 20 recovered (5 complete via the second copy); the other 8 lost the start of the compressed stream in every copy.

## Limitations / edge cases / version differences
- Two scoring schemas by map type: capture-point (`blue_points`/`orange_points`) vs payload (`payload`/`timers`). Parser must treat both as optional.
- Players may join/leave mid-match; slots (`playerid`) are reused. Key players by `userid`.
- Recording client usually appears in SPECTATORS; spectators are excluded from stats.
- `Weapon` may be empty string.
- Same `sessionid` may arrive in multiple files (different recorders or overlapping recordings).

## Legacy (`.ecrreplay`)
- C: bz2-compressed Python pickle: `{start_time, framerate, sessionid, players{slot→{name,playerID,level,number,ping}}, data[{teams[[{h,b,l,r,v,p}]]}]}`. Unpickling untrusted files is unsafe → **not supported** (Decisions D9).

## Open questions
| # | Question | Status |
|---|---|---|
| Q1–Q4 | Reference contents, reader, frame shape, old stats | Resolved by direct inspection (2026-10-29) |
| Q5 | How to determine the winner on payload maps? | Answered (A): see Payload semantics. Only one side attacks per recording; whether teams swap sides in a later recording is U |
| Q6 | Timezone of timestamps | Open — assume recorder local time |
