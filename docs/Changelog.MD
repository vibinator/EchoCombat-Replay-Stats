# Changelog

Working record of what changed in each release, newest first.

## Versioning (user, 2026-11-01)
- **Calendar versions:** `YYYY.MM.DD.N` = release date + the Nth update that day (`2026.11.01.6` = sixth update on
  1 November 2026), plus the release time. People see the short form `Beta v26.11.1-6` (footer:
  `Beta v26.11.1-6 · 1 Nov 2026, 16:59`); the full form tags Docker images, commits and these headings.
- Every update runs `python app/bump_version.py`: it sets `VERSION` and `RELEASED` in `app/backend/version.py` and adds
  the `## <version> — HH:MM` heading here; write the notes under it. Shown in the website footer (version, date and
  time), `/api/health` (`version`, `released`), the admin console, the Docker image tag and the GitHub commit label.
- Until 2026-11-01 versions were numbered Beta 1 – Beta 80 (no release times kept); their headings were renamed to the
  calendar version of the same day, with the old number beside it. The old git tags (`beta-45` …) still work.
- `PARSER_VERSION` / `STATS_VERSION` are separate, internal: they decide which replays are re-read (D19) and are only
  bumped when parsing or stat calculation changes.
- Entry format: what changed for the person using the site / console, then anything they must do (restart, wait for
  a re-read).

---

## 2026.11.10.48 — 23:33

- Home page heatmaps: the weapon, ordnance and tac mod choices no longer carry the small "cut" label (Starburst,
  Protostar, Quark ...). The label is unchanged elsewhere on the site.
- **To do after updating:** nothing beyond the restart of the earlier updates.

## 2026.11.10.47 — 23:30

- **Home page, Payload heatmap: it now shows the payload's speed.** "Speed" (the first choice) is the average
  speed of the payload at each point of its route, the moments it stands still or rolls back included, so a spot
  where pushes stall is dark and a spot it runs through is pale. "Speed while moving" leaves those moments out;
  "Rollback" stays. Each card gives the map's average: on the development PC's data Fission 0.51 m/s and Surge
  0.47 m/s (1.05 and 1.02 m/s while moving).
- **Removed: "Stops"** (the share of time the payload stood still), and **"Win / loss"** (winners and losers).
  Links with `heat=payload:stop` or `heat=result:...` open the Teams view.
- The all-time heat is counted again once after this update. **To do after updating:** restart the server.

## 2026.11.10.46 — 23:27

- **Play-area bounds corrected on Combustion, Fission and Surge.** Their x and z limits were swapped, so part of
  each map counted as out of bounds and simply crossing that line counted as a death. Found through the new Deaths
  heatmap: a straight line of deaths across Combustion (17 % of all its deaths). Dyson was right and does not change.

  | Map | Was (x, z) | Now (x, z) | Of the map counted out of bounds, was | Time in bounds, was → now |
  |---|---|---|---|---|
  | Combustion | -100..100, -20..60 | -20..60, -100..100 | 13 % | 63 % → 75 % |
  | Fission | -30..40, -80..130 | -80..130, -30..40 | 39 % | 34 % → 73 % |
  | Surge | -50..70, -60..150 | -60..150, -50..70 | 16 % | 57 % → 73 % |

  (Latest 300 matches per map; Dyson 76 %. Each box now holds its whole map and none of the rooms players are sent
  to between lives, 150-200 m away.)
- **Still boxes, not the real outline of each play area** (user: much better than before, but not right). The
  outlines are to be drawn by hand with the bounds editor (2026.11.10.49) and will replace the boxes; that will need
  the archive read once more, so it is worth waiting for them before restarting the live server.
- **What changes on those three maps:** deaths (estimated: Combustion about 7.3 → 6.6 per player per match, Fission
  5.1 → 5.5, Surge 4.5 → 5.0), time in bounds, and everything counted only in bounds: average and top speed, time
  stopped, upside down, near a teammate / enemy, arm, loadout shares. Death places on heatmaps and the timeline too.
- **Achievements that read these numbers** and may be reached more or less easily on those maps: Super Ultra Hyper
  Turbo, I'm Bat Bot (all three), Pew Pew Proof, Tech Support w/RAD_Natalie, Hug Your Frenemy, The Wings of
  RAD_Wyvern, Pixel Party!, Cyberkinetic Enhancements, Untouchable Chassis, Lone Echo, Boost Junkie, and the
  "at least 1 minute in bounds" rule (many Fission games failed it only because of the wrong bounds). Their targets
  were not changed here: look at them again once the archive has been read.
- **The whole archive is read again after this update** (stats version 12): it starts by itself at the next start,
  takes hours on the NAS, and old results stay visible until each replay is replaced. The same pass gives every
  match the exact upside-down data of 2026.11.10.43, so no separate `reprocess-all` is needed.
- When it has finished, delete `data/database/map-heat.npz`, `map-heat-30d.npz` and `map-heat-90d.npz` and open
  the home page (or wait for the next monthly count): the Deaths heatmap then loses its straight lines.
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.10.45 — 23:13

- **3D heatmaps are readable: they no longer draw every place ever visited at full strength.** A long history
  filled the whole map with a cloud of dots. (Player, Compare and match 3D heatmaps.)
  - **"Show" slider** in the bar under the view (and in the full screen options): how much of the heat is drawn,
    from only the busiest 2 % of each layer's places up to everything.
  - **Three buttons set it:** *Hot spots* (the busiest 5 %: where most time was spent), *Routes* (the busiest
    25 %: the usual routes and positions; this is how it opens) and *Everything*.
  - **Busy places are solid, rarely visited ones nearly see-through.** A place passed once was drawn at 40 %
    opacity; it is now about 5 %, rising to solid for the busiest place of the layer.
  - Each layer (team, weapon ...) is measured by itself, so a small layer keeps its own hot spots.
- Fixed: on a heatmap where some matches have no height, the note saying so was stretched into a dark panel over
  the left half of the 3D view.
- **To do after updating:** nothing but the update itself (website only; nothing is counted again).

## 2026.11.10.44 — 23:03

- **Match, player and Compare-page heatmaps: "Upside down" colouring.** One layer for upside down, one for
  upright, in 2D and 3D. It uses the exact data kept since 2026.11.10.43, so only matches processed since then are
  in it; older matches are left out of this colouring until the archive is read again (`reprocess-all`), and the
  page says so.
- **The same heatmaps: "Compare".** Tick it and pick two of the layers shown (blue and orange, two weapons, upside
  down and upright, two speed bands ...): pink where the first is relatively more often, green where the second
  is, with a swap button. Each layer is measured against its own total and smoothed over about half a metre
  (single paths are thin lines at 0.1 m cells). Worked out in the browser from the answer already loaded: no
  extra request.
- Not added here: "Handed". A player's arm is one setting per match, so on a player or match page it would only
  split whole matches, not places; it stays a home page heatmap (all players).
- **To do after updating:** restart the server.

## 2026.11.10.43 — 22:59

- **Upside down, exactly.** The position tracks of a match now keep who is upside down at every sample (the same
  test as the "Inverted" statistic: the body's up points down), so the home page's "Upside down" heatmap no longer
  depends on the 3D tracks. Every match processed from now on has it.
  - Matches processed earlier: the head's roll from the 3D tracks stands in where those exist (as before), and a
    match with neither is left out of that heatmap. **To give every match the exact data, read the archive again:
    console command `reprocess-all`** (hours on the NAS, old results stay visible meanwhile). Nothing is read again
    by this update on its own.
- **The monthly count of the all-time heat now counts everything again** instead of only adding new matches: what
  a match adds also comes from things that change when a replay is read again (winner, arm, deaths, upside down),
  and adding only new matches never picked that up. It is counted beside the old counts and takes their place when
  complete, so the cards never show a half-done picture; a restart half way carries on. On the development PC
  2.6 minutes for 29,817 matches; twice the memory (about 170 MB) while it runs. Time ranges are still brought up
  to date in place, daily.
- After a `reprocess-all`, the heat picks the new data up at the next monthly count; to have it at once, delete
  `data/database/map-heat.npz` (and `map-heat-30d.npz`, `map-heat-90d.npz`) and open the home page.
- The all-time heat is counted again once after this update. **To do after updating:** restart the server.

## 2026.11.10.42 — 22:52

- **Heatmaps kept on disk: the ones in use stay.** When the folder (`data/cache/answers`) was full, the files
  written longest ago went first: exactly the prepared heatmaps of top players who had not played lately, which the
  idle pass then built again every 6 hours. Now the files not *used* for the longest go first: a heatmap counts as
  used when it is read for a visitor or found still current by the idle pass.
- **NAS YAML: 4 GB for that folder** (`ECHOVR_ANSWER_CACHE_MB: "4096"` in `docker-compose.yml`; 1 GB when the line
  is not there). Expected use: 150-350 MB for the prepared heatmaps of the 100 most active players, the rest for
  whatever else people open (30-400 KB each).
- **To do after updating:** restart the server with the new `docker-compose.yml`.

## 2026.11.10.41 — 22:48

- **Player heatmaps (flat and 3D) are no longer worked out again without need.**
  - **Only when the player has a new match.** A kept heatmap was out of date as soon as anybody's replay came in,
    so with replays arriving all day it was rebuilt again and again. It now depends on that player's own matches on
    that map: a new, re-read or removed match of the player makes it out of date, nothing else does.
  - **Not at midnight.** For the period "All time" the kept heatmap is the same on every day (it used to be built
    fresh once each day).
  - **Not after a restart.** Heatmaps are also kept on disk (`data/cache/answers`, up to 1 GB, oldest out first;
    `ECHOVR_ANSWER_CACHE_MB`, `0` = off). After a restart they are read from there: 2-20 ms on the development PC
    instead of a full build.
- **The long heatmaps of the 100 most active players are built ahead of time.** After writing the height files
  (2026.11.10.38), the idle pass builds "All time, All matches, by team" (flat and 3D) for each of them on every
  map they played (about 400 player-map pairs) and saves them to disk only, so memory stays for what people are looking at. One that
  is still current is skipped; the pass runs only while no replay is being processed and rests as long as each
  build took. About 0.5 MB per player and map on disk.
- Not prepared ahead: other colourings (weapon, loadout, speed ...) and other periods. Those are built on first
  view (faster since 2026.11.10.37) and then kept like the rest.
- A 3D heatmap that leaves matches out because their 3D tracks are not there yet is looked at again once a day.
- **To do after updating:** restart the server. Nothing to set: the folder is made by itself. The first idle pass
  after the update takes a while (every long heatmap once); the log says how many were built.

## 2026.11.10.40 — 22:48

- **Home page heatmaps: time range.** "All time", "Last 90 days" or "Last 30 days", for every tab, the compare and
  the large view; the note says how many matches the pictures are counted from. In the address as `days=30`.
- The two ranges are brought up to date once a day (on the first visit of the day: the new matches added, those
  that left the range taken out again, a few seconds), all time once a month as before.
- No extra memory while nobody looks: a range's counts are loaded when it is asked for (0.35 s on the development
  PC) and let go ten minutes after the last request; its answers stay cached meanwhile. About 85 MB each while
  held, 4 MB each on disk. First build: 6-8 s here for about 1,000 matches.
- **To do after updating:** restart the server.

## 2026.11.10.39 — 22:42

- **Home page heatmaps: more to look at.**
  - **Win / loss:** where the winners and the losers of decided matches spend their time. Compared with each other
    it shows it at a glance: winners on the objective, losers on the way back from their spawn.
  - **Speed:** where players are stopped, slow, medium or fast (the same four bands as the match heatmaps).
  - **Deaths:** where players die, and (the default view) where they die more often than the time spent there
    would suggest. Deaths are estimates (the last spot before a player left the play area) and few per spot, so
    they are smoothed over about a metre. **Known flaw:** on Fission, Combustion and Surge straight bright lines
    show where the play-area bounds are set wrong (leaving them counts as a death); Dyson is not affected.
  - **Payload, "Rollback":** where the payload rolls backwards. Each payload card now also gives the map's own
    average (speed going forward, or the share of the time stopped / rolling back).
- **Large view: zoom, drag and read-out.** Buttons, a double click or Ctrl + wheel zoom in up to 8 times (the wheel
  alone once zoomed in, so the page still scrolls past the map), drag moves it. Pointing at a spot says what it
  means: "Pulsar: 1.4× as often as usual", "Winners: 1.5× as often here as Losers", "Blue 34 % · Orange 66 % of the
  time here", "Payload: standing still 24 % of the time".
- **Swap button** beside "Compare with": turns the two heatmaps around.
- **A view can be linked.** The address remembers the tab, the choice, what it is compared with and the open map,
  for example `/?heat=result:won&vs=result:lost&map=dyson`.
- Every choice is cached as before: built once per state of the counts on the server (about 0.15 s for the four
  maps), then served from memory with an ETag, by Cloudflare, and kept by the page while it is open.
- The all-time heat is counted again once after this update (new layers): some minutes in the background. About
  85 MB of memory (was 70), 9 MB on disk.
- **To do after updating:** restart the server.

## 2026.11.10.38 — 22:32

- **3D heatmaps of the 100 most active players are prepared while the server is idle.** Two minutes after a start,
  the server writes the missing `heights.bin` files (see 2026.11.10.37) of every match one of the 100 players with
  the most matches is in, newest first. So the first 3D heatmap of exactly the players with the longest histories
  is fast too, without running the backfill by hand.
  - Only while no replay is being processed, one match at a time, resting as long as each match took: at most half
    of one core. It stops with the server and carries on where it was after a restart (what is written stays).
  - It looks again every 6 hours for players who entered the top 100 since. The log says how many matches there
    were to write and how many were written.
  - `backfill_tracks3d.bat --heights` is still there to do every match of everybody at once.
- **To do after updating:** restart the server.

## 2026.11.10.37 — 22:28

- **Player 3D heatmap: much less work per match, so "All" no longer looks stuck.** Measured on the live site before
  this update, for a player with 1,975 matches on one map: last 20 = 0.6 s, last 200 = 1.8 s, last 1,000 = 9.4 s,
  All = 18.3 s (and the 2D heatmap is worked out at the same time). Nearly all of that was unpacking each match's
  3D track file (95 KB, 400 KB unpacked: every player's position, facing and hands) to get one player's height.
  - Each match now has a small `heights.bin` (a few KB) next to its tracks: the height of every player at every
    heatmap sample. The 3D heatmap reads that instead.
  - Counting the voxels is cheaper too (counted a part at a time instead of sorting every point at once; less
    memory for long histories).
  - The picture is the same to the last voxel (checked against the old code for team, weapon, loadout and speed
    colouring over 415 matches).
  - On the development PC: 415 matches 0.8-0.9 s → 0.35-0.5 s with eight reading threads; on one thread about
    2.9 ms → 1.1 ms per match. The live server has fewer cores, so expect about a third of the old times there
    (not measured live yet).
- New matches get their `heights.bin` when they are processed. For older matches it is written the first time a 3D
  heatmap needs the match, so the **first** view of a player is as slow as before and fast from then on.
- **To do after updating:** restart the server. To make every player fast at once, run
  `backfill_tracks3d.bat --heights` once where the data folder is (minutes: it reads only the track files, no
  replays, and can be stopped and run again).

## 2026.11.10.36 — 22:27

- **Home page heatmaps: three new tabs.**
  - **Handed:** where left-handed and right-handed players are (the arm setting of each player in each match; 8 %
    of the play time is left-handed). "Favoured spots" and "Everywhere", as for gear.
  - **Upside down:** where players are upside down, or upright. Read from the head's roll in the 3D tracks, so only
    matches that have 3D tracks count; the note under the cards says how many. Run `backfill_tracks3d.bat` to cover
    more of the archive, the next monthly count then picks them up. (Agrees with the "Inverted" statistic: correlation
    0.96 over 2,465 players; that statistic uses the body, this the head, so the share is a little lower.)
  - **Payload** (Fission, Surge): the payload's own movement as a band along its route. "Stops" = the share of its
    time it stood still at each point, "Speed" = its average speed going forward. Only between the payload's first
    and last move of a match, so the wait before the round and after the finish is not counted.
- **"Compare with": lay any heatmap against any other** (both teams, one team, any weapon, ordnance, tac mod,
  left / right-handed, upside down / upright). Pink = where the chosen one is relatively more often, green = where
  the other is, clear = about as often. Each is measured against its own total, so something rare compares fairly
  with something common. Examples: left-handed against right-handed, Comet against Nova, blue team against orange.
- The all-time heat is counted again once after this update (new layers): some minutes in the background, the cards
  fill in as it goes. On the development PC 111 s for 29,817 matches (was 96 s); longer where most matches have 3D
  tracks, since those files are read too. Saved counts 7.6 MB, about 70 MB of memory.
- **To do after updating:** restart the server.

## 2026.11.10.35 — 22:09

- **Home page, weapon / ordnance / tac mod heatmaps are sharper.** "Favoured spots" were smoothed over about a metre
  each way, so every spot was a round blob three to four metres across; they are now smoothed over one 0.3 m cell
  each way, as fine as the Teams view: single perches, doorways and routes show.
- Nothing is counted again: only the drawing changed. A choice is about 10 % larger to download.
- **To do after updating:** restart the server.

## 2026.11.10.34 — 22:01

- **Home page heatmaps are no longer faded.** Since the finer 0.3 m cells, the brightness was set by a handful of
  spots where somebody stood parked (30 to 280 times a usual cell), which left everything else at 10-20 % strength;
  Combustion was almost grey. The scale now ends at the busiest 1 % of cells instead of the busiest 0.1 %: a usual
  visible spot is drawn at 25-38 % instead of 9-22 %, the main routes at 54-70 % instead of 22-44 %.
- "Teams": quieter routes show more, and the busiest places keep their team colour instead of turning white.
- A gear's "Everywhere" view uses the same scale and is brighter too; "Favoured spots" did not change.
- Nothing is counted again: only the drawing changed.
- **To do after updating:** restart the server.

## 2026.11.10.33 — 21:37

- **Home page heatmaps are finer: 0.3 m cells instead of 0.5 m** (2.8 times as many), most visible in the large
  view. Not 0.25 m: positions are stored in whole decimetres, so those cells would show stripes.
- Cost: the monthly count takes about two thirds longer (96 s instead of 58 s on the development PC for 29,817
  matches), the saved counts are 6.5 MB and about 60 MB of memory; a choice of the four maps is 70-115 KB (about
  210 KB for a gear's "Everywhere" view).
- The all-time heat is counted again once after this update (cell size changed).
- **To do after updating:** restart the server.

## 2026.11.10.32 — 21:32

- **Fission is no longer upside down.** Its minimap and every position drawn on it were turned top to bottom
  together, everywhere the 2D map is shown: home page cards and large view, match cards, match and player heatmaps,
  the timeline and 2D playback. Positions still land on the map as before (99.6 % of all samples on the picture);
  the 3D views were not affected and did not change.
- The home page's all-time heat is counted again once after this update (the saved counts were for the old
  picture): some minutes in the background on the NAS, the cards fill in as it goes.
- The Fission picture has a new address (`?v=2`), so no browser or Cloudflare copy of the old one is shown under
  the new positions.
- **To do after updating:** restart the server.

## 2026.11.10.31 — 21:22

- **Home page, "Matches per map": click a map's picture to see its heatmap large.** It opens under the four cards,
  over the full-size minimap, and follows the same tabs (Teams / Weapon / Ordnance / Tac mod, the gear row, Favoured
  spots / Everywhere). Click the picture again, press Esc or use Close to shut it. The map's name and match count
  still lead to that map's matches; the picture no longer does.
- A lone player parked beside the map (Surge had one) no longer shows as a bright dot in a gear's favoured spots.
- **To do after updating:** restart the server.

## 2026.11.10.30 — 20:57

- **Home page heatmaps reviewed and reworked** ("Matches per map").
- **Gear heatmaps now show each item's favoured spots**: where a weapon, ordnance or tac mod is held more often than
  on the map as a whole. Before, every piece of gear looked the same (the objective and the payload's route, where
  everybody is). Now each has its own picture: the Comet's sniper perches, the Stun Field on the flanks, the Arc Mine
  around Dyson's centre. A "Favoured spots / Everywhere" switch beside the gear brings the old picture back.
- **Team heatmap is clearer**: the grey wash over the whole map is gone, each spot takes the colour of the team that
  is there most, and the busiest spots turn towards white.
- Gear held less than 0.5 % of the time (Blazar, Dot Field, Attack Drone, Overcharge, Umbral Veil, Neutron) is no
  longer offered: too little data to draw.
- One spot where somebody stood for hours no longer lights a square on the map (Surge had one).
- A colour scale beside the note under the cards; the choice of view sits beside the gear, next to the title.
- Pictures are smaller (5-30 KB per map). Nothing is counted again: the same saved counts are drawn differently.
- `GET /api/overview/map-heat` takes `view=favoured|all` (gear only).
- **To do after updating:** restart the server.

## 2026.11.10.29 — 20:21

- **Home page, "Matches per map": the map cards are a little larger and each shows an all-time heatmap** over its
  minimap: where players have been in every counted match (duplicate recordings left out), blue and orange team,
  brighter where they are most.
- **Heatmaps per weapon, ordnance and tac mod.** The tabs beside the title (Teams / Weapon / Ordnance / Tac mod) and
  the row of gear under them switch all four cards to where players were while holding that piece of gear (dark violet
  = rarely, pale yellow = most). Gear is listed most held first; gear nobody ever held is not offered.
- **Counted once a month** (first visit of a new month), in the background: only matches added since the last count
  are read, and the cards keep showing the previous picture meanwhile. The line under the cards says when it was last
  updated. The very first count reads the whole archive (57 s on the development PC for 29,817 matches; expect some
  minutes on the NAS) and the cards fill in as it goes.
- Kept light: the counts live in one small file (`data/database/map-heat.npz`, about 3 MB; delete it to count again from
  nothing) and about 25 MB of memory; a choice is one request of about 90 KB for the four maps, answered from the cache.
- New: `GET /api/overview/map-heat?layer=team|weapon:<code>|ordnance:<code>|tacmod:<code>`.
- **To do after updating:** restart the server.

## 2026.11.10.28 — 18:23

- **The 22 Experimental gear challenges now end in their item type: "(Weapon)", "(Ordnance)" or "(Tac Mod)"**, like the Gear
  mastery ones (Translocator's "Beam Me Up" already had it). Weapons: Starburst, Protostar, Quark and Blazar (and
  Forbidden Arsenal). Ordnances: Translocator and Dot Field. Tac mod: Overcharge (Overclocked, Full Charge, Charged Up).

## 2026.11.10.27 — 18:22

- **Renamed Point Taker and Point Guard to "Point Taker (Capture Point)" and "Point Guard (Capture Point)"**, like the other
  Capture Point challenges. (Every Payload challenge already had its "(Payload)" tag.)

## 2026.11.10.26 — 18:19

- **The 25 award-card challenges now end in "(Leaderboard)"** (for example "MVP of Echo Combat (Leaderboard)"), like the
  "(Weapon)" and "(Combat)" ones, so it is clear they come from the recorder's award cards.

## 2026.11.10.25 — 18:18

- **Renamed "Saturn Super Star" to "Super Star"** (Combat, one game).

## 2026.11.10.24 — 18:16

- **One set of period names everywhere: One Match, One Day, One Week, Cumulative** (the Achievements tabs and the
  "Coming soon" page used different wording). The "Coming soon" page also gets some hype: "N challenges to conquer", a
  line under each period card ("Own the day", "Seven days of glory" ...) and a more excited One Match line.

## 2026.11.10.23 — 18:14

- **"Coming soon" sneak peek: one list of challenges.** The "Classic challenges" and "New challenges" sections are merged
  into a single "Challenges" count with one card per period (In one game, In one day, In any 7 days, All time); original,
  new and Combat challenges are counted together. The per-theme cards are gone.

## 2026.11.10.22 — 17:59

- **The "Coming soon" sneak peek now counts the Combat challenges** (a "Combat" card under New challenges, and in the
  "In one game" total) and no longer mentions ECRanked: "Classic challenges" replaces "From the original ECRanked
  site", the "new" tag says "A newer challenge", and the "built on replay data the original site never read" line is gone.

## 2026.11.10.21 — 17:56

- **25 new Combat challenges for the game's award cards.** One game, one medal each for winning the card (16: MVP, Guard,
  Specialist, Medic, Cannoneer, Tank, Hot Shot, Defender, Assassin, Sniper, Renegade, Controller, Super Star, Shock
  Trooper, Infiltrator, Immovable Object; a card can only be won once per game). Longer ladders only where players win
  enough cards: MVP (one day, any 7 days, all time), Guard and Medic (any 7 days, all time), Specialist and Hot Shot
  (all time). The rarer cards (Tank and Sniper included) are one-game medals only. Targets come from the 154 matches with cards so far (the
  top 10 % of players with 10+ games). Provisional like the other Combat challenges. Nothing to restart or re-read.


## 2026.11.10.18 — 17:43

- **The "Month" page is gone: its five Combat challenges are now "any 7 days" ones** (Power Surge, Captain Rhodes' Right
  Hand, Lobby Billboard, Above the Rings, Kronos II Medbay), with the targets scaled to 7 days (all their all-time
  versions already existed). Progress and medals already earned on them are recalculated by the next ranking refresh.

## 2026.11.10.17 — 17:31

- **Achievements page: less empty space.** The row of stat cards under "Your next medals" (Average progress,
  Completed, Bronze, Silver, Gold, Crown) is gone. Average progress and completed now sit in the medal bar's header
  line (`51% average progress · 36 / 158 completed · 24 / 158 crowns`), and the per-medal counts were already in the bar.
  The "N or better" tier counts are no longer shown.

## 2026.11.10.16 — 17:20

- **A player's Achievements page now opens with the medal bar from the player page, bigger.** One bar across the page
  split by best medal (crowns, gold, silver, bronze), with the overall progress, the crowns out of all challenges and
  the count per medal under it, above "Your next medals". The player page's strip is unchanged (both use the same
  component). Checked on desktop (dark and light) and at phone width.

## 2026.11.10.15 — 17:15

- **Less NAS CPU: the achievement ranking is recalculated at most every 15 minutes** (was 5; user, 2026-11-10). The
  achievement leaderboard, the rarity shares and the medal feed can be up to 15 minutes behind new matches; a player's own
  achievements page is not affected. Each refresh reads every game of every player (3.5 s of CPU on the dev PC, an
  estimated 18-42 s on the NAS): during play roughly 2-5 % of one NAS core instead of 6-14 %. New setting
  `ECHOVR_RANKING_REFRESH_S` (seconds, `900`); it is never shorter than `ECHOVR_CACHE_REFRESH_S`.
  To do: nothing (900 is the default without the YAML line); to choose another interval add the line from the new YAML.

## 2026.11.10.14 — 16:57

- **Medal ladder is now Bronze > Silver > Gold > Crown (pink)** (was bronze, gold, platinum, crown): same targets, new
  names and colours (old gold is silver, old platinum is gold). Texts that said "gold or better" / "gold and up" now say
  silver (Medal Collector, 7-day gear rules). The teal platinum colour is gone.
- **The crown medal is now pink everywhere** (was gold with a pink diamond): the player-profile Achievements strip
  (bar and legend dot), the crown medal picture, crown names and icons on achievement cards, recent unlocks, medal
  chips and dots, and the Medals help text. A lighter pink in the dark theme, a deeper one in the light theme.

## 2026.11.10.13 — 16:52

End-to-end performance test of the site (live sweep, local load tests on a copy of the full archive, browser tests).

- **"Server busy" fixed at its main cause: achievements are no longer calculated inside the web server.** The
  everyone-ranking (leaderboard, rarity, recent medals) is pure Python, and Python runs one thread at a time: while the
  web server built it, every other request waited its turn. Measured on the dev PC: 16x fewer requests answered, stalls
  of 1.5 s; on the live NAS during the test ordinary requests took 6-36 s and one timed out. The ranking and the
  achievement page of players with 100+ games are now calculated in the import worker's low-priority helper processes;
  the web server only waits for the result. Same test after the change: no slowdown at all (worst stall 42 ms). The
  results are identical (compared on the full archive: 8,618 players, 19,164 medals).
- **An update of the site no longer throws the saved achievement results away.** They were tied to the app version, so
  after every update all 8,600 players were evaluated again: 72 s of CPU on the dev PC, minutes on the NAS, each time.
  They are now tied to the rules and the code that evaluates them, and the medal times are saved too: after a restart
  the ranking is ready in 5.6 s (dev PC), in the background. The first start after THIS update evaluates everyone once
  more (in the helper process: the site stays quick meanwhile).
- **Each ranking refresh uses about 20 % less CPU** (4.4 s -> 3.5 s on the dev PC; it runs at most every 5 minutes while
  new matches arrive).
- **A ranking that is not ready yet answers "being calculated, try again in a minute"** after 20 s instead of holding the
  request (and a server thread) for as long as the build takes. The achievements list and the medal feed never wait for it.
- **"Something went wrong showing this page" after an update, fixed.** A tab that was open while the site was updated
  kept its old pages, whose files no longer exist on the server: opening another page ended in that message until a
  manual reload. Now every answer of the server names its version (`X-EchoVR-Build`); a tab that sees a newer one
  reloads itself on the next page change, and a page file that cannot be loaded reloads the tab once. An answer
  Cloudflare kept from before the update is asked for again. A page that still crashes forgets its saved answers and
  tries once more before showing the message; the Reload button forgets them too (a plain reload handed the page the
  same saved answer again). Never more than one automatic reload a minute.
- Tested: 7 browser tests of these cases (missing page file, file gone for good, newer server, older copy, crash on a
  bad answer, crash every time), 33 page views of every page without a page error, 5 new backend tests.
  To do: nothing on the NAS beyond the usual update (no YAML change).

## 2026.11.10.12 — 16:37

- **Cloud: "Upload files" opens the file dialog reliably.** The hidden file inputs sat inside the clickable upload box, so
  each button's click on its input came back through the box's own click handler, which could open or cancel a second
  dialog. The inputs now sit outside the box and the buttons stop their click there. Checked in Chromium and Firefox:
  "Upload files", "Upload folder" and the box itself each open exactly one dialog of the right kind, also one after another.

## 2026.11.10.11 — 15:34

- **Fix: a bio written on My profile now shows on the player's page.** When a Discord account was connected to its player
  only through the Echo account seen on the match list (no bot link, and an older player id that is not the Discord id), the
  bio was saved but the player page did not look for it, and its editor refused the owner. The player page now finds that
  account's bio (the same way it already found the picture), the owner can edit it there, and My profile links to it.
- **Cloud: clicking anywhere on the upload box opens the file dialog again** (as before the folder buttons), Enter / Space
  too. Fixed on the way: the "Upload folder" button could open the file dialog instead of the folder dialog.
- **Faster first response after a quiet spell (NAS YAML).** Measured: after 45 s or more without visitors, the next request
  waited 1.6-4.3 s (after 20 s: 0.1 s) while the Cloudflare tunnel's UDP (QUIC) connection, dropped by the home router, came
  back. The tunnel now uses HTTP/2 over TCP (`--protocol http2` on the cloudflared service), which routers keep open.
  To do: paste the new YAML (only the cloudflared `command:` line changed; keep your secrets), Recreate.

## 2026.11.10.10 — 15:15

- **NAS YAML tuned for 31 GB of RAM (user, 2026-11-10).** `ECHOVR_TRACK_CACHE_MB` 512 -> 3072 (every match's position data
  stays in RAM: faster heatmaps and playback), `ECHOVR_DB_CACHE_MB` 1024 -> 2048 (room as the archive grows; shared cache,
  given back when needed). Virus scan limit 100 MB -> 1 GB: `ECHOVR_CLAMAV_MAX_MB: "1024"`, and the clamav service adds
  `MaxFileSize 1024M` / `MaxScanSize 2048M` to its own config at start (ClamAV cannot scan files over 2 GB at all). About
  3-4 GB more RAM in use. Files over 1 GB are labelled "Not scanned".
  To do: paste the new YAML in Container Station (keep your real secrets and VirusTotal key), Recreate.

## 2026.11.10.9 — 15:06

- **Virus and malware scanning of cloud uploads.** Two scanners:
  - **ClamAV** (new `clamav` container in the NAS YAML, updates its virus list by itself): every upload of up to 100 MB
    is checked **before** it can be downloaded. Meanwhile it shows as "Checking for viruses" on the Cloud page (no download,
    no changes); a file it replaces stays available until the new one is clean. One file at a time, so the NAS keeps its CPU.
    If ClamAV is down, files wait and are checked when it is back (they survive restarts).
  - **VirusTotal** fingerprint check in the background (needs your free API key in the YAML): only the file's SHA-256 is
    sent, never the file; results of about 70 engines for files seen before. 3 or more engines = quarantined. Paced to the
    free key (1 every 15 s, 480 a day); files over 650 MB are skipped (VirusTotal cannot know them).
  - A virus goes to the **quarantine**: Console > Cloud > **Quarantine** (console users only) shows both scanners' state,
    the files found, **Delete** or **Release** (false alarm), and **Scan all existing files** for what was uploaded before.
    Every scan, find and decision is in the Cloud audit log.
  - Files over 100 MB are labelled **"Not scanned"** (ClamAV's own limit; it would otherwise call them clean unchecked).
- **Fix found while testing:** two uploads finishing at the same moment could, with scanning on, put one file beside the
  cloud folder instead of inside it. Waiting, recycle bin and quarantine boxes now appear complete or not at all.
  To do on the NAS: paste the new YAML (the `clamav` service and the `ECHOVR_CLAMAV` / `ECHOVR_VIRUSTOTAL_KEY` lines), replace
  `YOUR_VIRUSTOTAL_KEY` with your key, Recreate. ClamAV's first start downloads its virus list (a few minutes; uploads wait).
  Then Console > Cloud > Quarantine > **Scan all existing files** once.

## 2026.11.10.8 — 14:44

- **Cloud recycle bin.** Delete on the Cloud page now moves the file or folder to a recycle bin instead of erasing it.
  Console > **Cloud** > **Recycle bin** lists what was deleted, by whom and when, with **Restore** (back where it was; a new
  name if something new took it, its folders made again if needed) and **Delete forever** / **Empty the recycle bin**.
  Items go for good after 30 days (`ECHOVR_CLOUD_TRASH_DAYS`). The recycle bin counts toward the 250 GB; the Cloud page
  shows how much of the space it holds. Restores and removals are in the Cloud audit log.
- **Uploads continue where they stopped.** A dropped connection is retried 6 times (2 s to 1 min apart) and only the
  missing part is sent again; choosing the same file again later (even after closing the tab, within a day) continues it.
  Downloads already resume with the browser's own Resume button.
- **Less NAS CPU for files** (dev PC, same test before and after): download 1 GB 81 % less CPU, folder of 300 small files
  64 % less (and 2.8x faster), upload 1 GB 25 % less. Done by: a running total of the space used instead of counting every
  file before each upload; the permission check once per file, not per 16 MB; 1 MB disk writes and download blocks instead
  of 64 KB; deleting is one rename (instant, even for a big folder). An upload no longer asks Discord for the person's roles
  once per file (a 300-file folder was 300 Discord requests).
- **Fix:** uploading a folder could refuse some files as "outside the cloud folder" when several of its subfolders were
  created at the same moment (seen on Windows). The path check now looks at each part for links instead.
  To do: nothing.

## 2026.11.10.7 — 14:27

- **Cloud: many files and whole folders at once.** New **Upload folder** button (Windows' folder dialog) next to **Upload
  files** (the file dialog, several files at once). Dropping folders on the page works too, folders inside folders and empty
  folders included; the folder tree keeps its shape. More files can be added while an upload runs; 3 files go at once. One
  summary line ("12 of 340 files done · 3 sending · 1.2 GB of 3.4 GB") with the files being sent and any that failed, plus
  "Try the failed ones again". Names already in the folder: asked once whether to replace them. Closing the tab during an
  upload asks first.
  To do: nothing.

## 2026.11.10.6 — 13:49

- **Discord request limits, so the bot is never flagged.** Every request the site sends to Discord (logins, role checks,
  pictures, the member list) now goes through one limiter: at most 5 a second for the whole site (Discord allows 50 per bot,
  and the site shares the token with your Discord bot), short bursts up to 10. If Discord ever says "slow down" (429), every
  Discord request waits as long as Discord asks. If Discord refuses 500 requests within 10 minutes (it blocks an IP at
  10,000), the site stops asking Discord for 10 minutes and logs it, which protects your home IP and the bot. The server's
  role list (Permissions page) is remembered for 5 minutes. A request that cannot get a turn within 2 seconds acts like
  Discord being unreachable: role checks keep their last answer, pictures stay as saved.
  To do: nothing.

## 2026.11.10.5 — 13:44

- **Player pictures are fetched only when someone opens that player's profile page.** The Players list, Leaderboard,
  Achievements and search show the pictures the site already has (even older than a day) and never ask Discord; a player
  whose profile nobody has opened yet has no picture there until someone does. Nothing is fetched at startup or in the
  background any more. Profile pages also now find the picture of a player whose id is their Discord id, as the lists did.
  To do: nothing. Pictures appear in lists as people open profiles.

## 2026.11.10.4 — 13:39

- **Discord pictures with fewer Discord requests.** A player picture looked up from Discord is now remembered for 24 hours
  (was 1 hour) and saved in the data folder (`data/discord-avatars.json`), so restarts and updates no longer ask Discord for
  every picture again. Saving your profile still updates your picture at once.
- **No more repeating Discord warning.** Matching pictures to unlinked players by name needs the bot's Server Members intent.
  Without it, Discord's refusal is now logged once per start instead of every 10 minutes, and list pages stop re-asking for
  pictures every 20 seconds. All other pictures (linked players, known Discord ids) need no special permission and keep
  working. New setting `ECHOVR_DISCORD_NAME_PICTURES` (default on; `0` = never ask for the member list).
  To do: nothing. For name-matched pictures, turn on the bot's Server Members intent (Developer Portal > Bot).

## 2026.11.10.3 — 13:16

- **Open Cloud audit log.** Console > Audit log > **Cloud audit log** lists every upload, download, new folder, rename and
  delete, and every refused attempt by someone logged in (no permission, no space, a bad name), with the person's Discord
  name and id, the time, the size and their IP address. Searchable. Only console users can see it.
- **Open Cloud fixes from end-to-end testing:**
  - Big uploads on fast connections no longer stop at about 2 GB: upload chunks from a logged-in person skip the per-visitor
    rate limit (still on for everyone else), and the page waits and retries if the server says it is busy.
  - Uploads running at the same time can no longer go over the 250 GB limit together: an upload reserves its full size when
    it starts. Unfinished uploads release it after 2 hours untouched (was a day).
  - Folders with thousands of files list about 20 times faster (5,000 files: 1.2 s → 0.06 s on the dev PC).
  - Cloud page: row lines run the full width, dates use the site's format, the folder path shows only inside a folder.
  To do: nothing beyond the normal update. The new audit log table is created by itself on start.

## 2026.11.10.2 — 12:50

- **Open Cloud space raised to 250 GB** (was 50 GB). It is one total for all files together, not per file or per person.
  To do: nothing, unless the NAS YAML sets `ECHOVR_CLOUD_QUOTA_GB` (then set it to `"250"` there).

## 2026.11.10.1 — 12:41

- **New: Open Cloud file storage (D60).** A **Cloud** tab for people logged in with Discord who have one of two new
  permissions on Console > Permissions: **Cloud view** (see and download files) or **Cloud edit** (also upload, make
  folders, rename and delete). Console users have both. Files are kept in the data folder on the NAS (`data/cloud`),
  up to 50 GB (`ECHOVR_CLOUD_QUOTA_GB`). Files of any size upload in 16 MB pieces with a progress bar; drag and drop
  works. Downloaded files never open as a page on the site. Every change is logged with who made it.
  To do: nothing to restart beyond the normal update. Give Cloud view / Cloud edit to the right roles or people on
  the Permissions tab. Optional: add `ECHOVR_CLOUD_QUOTA_GB` to the NAS YAML to change the 50 GB limit.

## 2026.11.09.16 — 13:13

- **51 challenges renamed (user's picks, 2026-11-09).** Every name now carries an Echo Combat word and ends with its category in
  brackets, like (Payload), (Combat) or (Weapon). The two challenges both called Immovable Object now have different names. Only the
  shown name changed: ids, progress and medals are the same. Nothing to restart or re-read.
  On a Roll → Echo Streak (Wins); Centurion → Centurion Bot (Wins); Clean Sweep → Capture Point Clean Sweep (Capture Point); Special Delivery → Payload Delivered (Payload); Hold the Line → Payload Shutout (Payload); Pedal to the Metal → Payload Pedal to the Metal (Payload); Immovable Object → Payload Roadblock (Payload); Freight Train → Payload Freight Train (Payload); Dance Floor Legend → Lobby Dance Floor Legend (Emotes); Beam Me Up → Beam Me Up, Translocator (Ordnance); Arsenal Overload → Kronos II Armory Raid (Weapon); Ordnance Overload → Bomb Bay Overload (Ordnance); Regular → Lobby Regular (Activity); Daily Grind → Ready Every Dawn (Activity); Time Well Wasted → Time Well Wasted on Kronos II (Activity); Overtime → Overtime on Kronos II (Activity); Hot Day → Hot Day Bot (Wins); Cargo Hauler → Payload Hauler (Payload); Grand Tour → Four-Map Tour (Map); Weapons Master → No Gun Left Behind (Weapon); Loadout Scholar → Loadout Scholar Bot (Loadout); Immovable Object → Nothing Leaves Kronos II (Payload); Untouchable → Untouchable Chassis (Wins); Comeback Kid → Capture Point Comeback (Capture Point); Statue → Space Statue (Movement); Lone Wolf → Lone Echo (Movement); Ambidextrous → Ambidextrous Bot (Movement); Speed Demon → Boost Junkie (Movement); Contested Ground → Contested Point (Capture Point); One-Trick Pony → One-Trick Pony (Loadout); Loadout Roulette → Quick-Change Chassis (Loadout); Mime Troupe → Lobby Mime Troupe (Emotes); Showboat → Showbot (Emotes); Frag Out → Chassis Crusher (Combat); Heavy Hitter → Hull Breach (Combat); Net Positive → Net Positive Bot (Combat); Objective Threat → Point Denied (Combat); On the Objective → Parked on the Point (Combat); Flawless → Flawless Chassis (Combat); Kill Spree → Kill Spree Bot (Combat); Busy Hands → Helping Hands of Kronos II (Combat); Body Count → Ring Debris (Combat); Force Multiplier → The Whole Echo Crew (Combat); Demolition Crew → Kronos II Salvage (Combat); Top Fragger → Top Bot (Combat); Triple Threat → Saturn Trifecta (Combat); Selfless → Service Android (Combat); Siege Breaker → Siege Breaker Bot (Combat); Field Medic → Repair Matrix Medic (Combat); Shock Trooper → Stun Field Trooper (Combat); Both Hands → Two-Handed Bot (Movement).

## 2026.11.09.15 — 12:56

- **Four of the new Combat challenges are removed as too repetitive:** Kronos II Mining Quota (damage in any 30 days), No Cargo Leaves
  Saturn (objective eliminations in any 30 days), Defender of Kronos II (total objective eliminations) and Strip Miner (total objective
  damage). Over 30 days or more these totals rise almost exactly with kills and damage, which other challenges already count. 16 new
  Combat challenges remain. Nothing to restart or re-read.

## 2026.11.09.14 — 12:48

- **The 20 new Combat challenges have new names from Ready At Dawn, Lone Echo, Echo VR and Echo Combat.** One game: Jack's Toolkit
  (was All-Rounder), Ghost of Sparta (Untouchable). One day: Wrath of Saturn (Wrecking Ball), Fission Reaction (Objective Grind),
  Camping Out on Dyson (Hold the Line), Keeping Liv Alive (Triage), Spontaneous Combustion (Hot Hand). Any 30 days: Power Surge
  (Campaign), Captain Rhodes' Right Hand (Backbone), Kronos II Mining Quota (Artillery), No Cargo Leaves Saturn (Siege Season),
  Lobby Billboard (Headliner), Above the Rings (In the Green), Kronos II Medbay (Field Hospital). All time: Defender of Kronos II
  (Objective Veteran), The Anomaly Doesn't Move (Holding Ground), Strip Miner (Siege Engine), Life Support Systems (Lifeline),
  Old Arena Habits (Live Wire), Ready At Dawn (Positive Record). Targets are unchanged. Nothing to restart or re-read.

## 2026.11.09.13 — 12:43

- **The new Combat challenges' crowns are now set so about the top 10 % of regular players (10+ counted games) can reach them.** One game
  and one day: what the top 10 % have reached. Any 30 days and all time: the top 10 %'s pace so far over 30 days and over about 3 months
  (the challenge period). Lower medals moved with the crown. "Any 30 days" stays a rolling window. Nothing to restart or re-read.

## 2026.11.09.12 — 12:40

- **20 new Combat challenges, and a new "Month" page on the Achievements page.** All come from the recorder's match reports only, like
  the other Combat challenges, and like them they don't count toward overall progress, totals or Medal Collector. Targets are
  provisional, set from 435 reports (4-9 Nov, 1451 counted games); see the next entry for the top-10 % crowns.
  - In one game: All-Rounder (kills, assists and objective eliminations, the lowest of the three counts), Untouchable (kills while dying 3 times or fewer).
  - In one day: Wrecking Ball (damage), Objective Grind (objective eliminations), Hold the Line (minutes on the objective), Triage
    (heal bubbles), Hot Hand (top-fragger games).
  - In any 30 days (new period, rolling like "any 7 days"): Campaign (kills), Backbone (assists), Artillery (damage), Siege Season
    (objective eliminations), Headliner (top-fragger games), In the Green (games with more kills than deaths), Field Hospital (heal bubbles).
  - All time: Objective Veteran (objective eliminations), Holding Ground (minutes on the objective), Siege Engine (objective damage),
    Lifeline (heal bubbles), Live Wire (stuns), Positive Record (games with more kills than deaths).
  Nothing to restart or re-read: the cards appear when the new version runs.

## 2026.11.09.11 — 12:03

## 2026.11.09.10 — 11:25

- **"More stats" and "Show more" are now panes in the card grid, not dropdowns under it.** On the player page a "More stats +13" card
  sits after the six headline cards; on the combat tab a "Show more +N" card sits after the awards won. Each is the same size and shape
  as the cards beside it, opens the extra cards in the same grid, and turns into "Show less / Hide" to close them again. Nothing to
  restart or re-read.

## 2026.11.09.9 — 11:16

- **Player page, combat tab: only the awards a player has won are shown as cards.** The ones never won (0) are folded under
  "Show more (N not won yet)"; a player with none sees "No awards won yet." and the fold. Nothing to restart or re-read.

## 2026.11.09.8 — 11:14

- **Combat stats: "Kills by weapon", "Deaths by weapon" and "Shots by weapon" show the top 5 weapons** (was 8), on the player page and
  per player on a combat match. Nothing to restart or re-read.

## 2026.11.09.7 — 11:09

- **Player page, combat tab: the Awards block is now the first thing under "Combat stats", for every player.** All 16 awards with how
  often each was won (0 when never), the line saying how many matches carry award data, and the "How the game's awards are earned"
  guide. Before, it sat below the counters and only appeared once one of the player's matches had award data, so most players saw
  nothing. The counters follow under a new "Game counters" heading. Nothing to restart or re-read.

## 2026.11.09.6 — 11:04

### Player page: easier to read
- **Six headline cards, the rest under "More stats".** Games, win rate, hours played, top speed, average speed and wins – losses stay
  at the top. The other cards (ping, packet loss, idle, inverted, near a teammate / enemy, emotes, arm, modes...) are folded under a
  "More stats (N)" line, so the tabs are no longer pushed far down the page, especially on phones.
- **A line under the period / map filter says what it changes.** It names the stats and the open tab when they follow it, and says
  so when a tab has its own time choice (Trends, Played with), always counts all time (Achievements) or has its own map picker
  (Heatmap).
- **"From the game" in the header:** K/D, kills, MVPs and awards from the game's own counters, all time, with an ⓘ saying it is a
  separate source from the replay stats. Clicking it opens the combat tab. Shown only for players with recorder reports.
- Nothing to restart or re-read.

## 2026.11.09.5 — 10:53
- **Player page, Combat tab: the Awards block now lists all 16 of the game's awards**, with 0 (dimmed) for the ones the player has
  not won yet, most-won first. Before, only the awards won were listed. Nothing to restart or re-read.

## 2026.11.09.4 — 10:41
- **Combat stats: the game's end-of-match awards.** The recorder now writes the award cards the game shows on the scoreboard (MVP,
  Assassin, Cannoneer, Super Star, Hot Shot, Sniper, Renegade, Specialist, Shock Trooper, Medic, Tank, Guard, Defender, Controller,
  Infiltrator, Immovable Object), and the site shows them:
  - Player page → Combat tab: an "Awards" block with one card per award won and how often, an "Awards" column in "Recent combat
    matches", and a fold-out guide that explains how every award is earned.
  - Combat match page (and the match page's Combat tab): the cards as the game handed them out, with the winner and the value that
    won it; badges beside the player names in the scoreboard.
  - Leaderboard → Combat: two new stats, "Awards" and "MVP awards", an "Awards" column, and the same guide under the table.
  - How they are earned (also on the site): there are no thresholds. MVP goes to the highest score; each other card goes to the player
    with the highest value of that stat in the match, and the game picks up to three of those categories to show. A match that ended
    empty hands out none.
- Only reports written since 9 November 2026 carry the awards; older ones show "older reports do not carry the awards" / no award
  column. Awards are not achievements (no medal uses them yet).
- After updating: the combat tables are rebuilt and every match report is read again (`COMBAT_VERSION` 2); that takes under a
  minute. Replays are not touched.

## 2026.11.09.3 — 02:09
- **Achievements page: "Recent medals" cards now look like the "Top players" cards.** Same layout, top-aligned: date, avatar and
  name, the medal icon with the challenge name in large type, then "earned <tier>" and the rule text in muted lines. Nothing to
  restart or re-read.

## 2026.11.09.2 — 02:05
- **Home page "Latest matches" (and "Recently played") update within about a minute.** They used to come with the overview, which is
  rebuilt in the background only once it is 5 minutes old, so a new match could take 6–8 minutes to appear. The list is now asked on its
  own (`GET /api/overview/latest`, a few rows via the `started_at` index, no archive-wide queries) every minute while the tab is
  visible. Nothing to restart or re-read.

## 2026.11.09.1 — 01:53

## 2026.11.08.1 — 00:10

### Replay viewer: fixes and small features (full test of the 2D and 3D playback, 2026-11-08)
- **Capture point scoreboard:** the third round was labelled "Round 2"; it now counts up to Round 3 and, once a team has its two rounds,
  says "Blue wins 2 – 1" (the capture percentages stay beside it).
- **Letting go of a player while riding with them works (3D):** Esc, clicking the highlighted name or choosing "None" while the camera was
  Follow or First person used to pick another player at once. Now the camera goes back to Orbit and nobody is highlighted. In compare
  mode (one camera for both sides) the ride simply goes on.
- **Clip links:** after a shared clip (`?until=`) had played, Play did nothing. The stop now applies once; Play carries on with the rest
  of the match.
- **Scrubbing keeps playing:** dragging the slider while the match plays no longer pauses it (the moment ticks, death chips and fight
  buttons still pause, so the moment can be looked at). Same in compare mode.
- **Click a dot on the 2D map** to highlight that player (within a few pixels; click again to let go). Before, only the roster could.
- **Death ticks under the slider** say who died when (hover) and jump there when clicked, like the round / checkpoint dots.
- **New keys:** `,` / `.` step one recorded position back / forward (half a second, paused), Home / End jump to the start / end.
  Listed in the footnote and the 3D "?" list.
- **Roster:** a player who is not on the map now reads "not arrived yet", "off the map (spawn room)" or "left" instead of
  "off the map / left" for all three.
- **Light theme, 3D view:** the camera bar, the controls card, the "?" list and the full-screen play controls were dark text on the
  dark stage; they now use the dark theme's colours on both themes.
- **Phones:** the deaths summary no longer stacks one time chip per line (the chips wrap under the name); the 3D camera bar wraps to
  two rows instead of scrolling out of sight.
- Housekeeping (2D): the map canvas was thrown away and made again on every frame; it is only resized when its size changes. The
  deaths / team fights section is no longer re-rendered on every tick of the clock.
- Nothing to do after updating; no replay is re-read.


## 2026.11.07.4 — 23:42

### Achievements page (user, 2026-11-07; mock-ups approved before the change)
- **Your next medals:** with a player selected, the page opens with the five challenges nearest to their next medal (closest
  first): the tile, the medal being chased and what is missing ("4.7 % more to reach bronze (95 % of the way)").
- **Medal dots on every tile:** four dots beside the percentage show the ladder (bronze, gold, platinum, crown): filled = earned,
  half = the one being chased. The exact targets stay in the tile's card.
- **Mega Prizes as a banner:** one line (period, the two prizes, the leader) with Show / Hide. Open by default only while the
  prize period runs; a visitor's choice is remembered in their browser.
- **Removed:** the theme chips under the period tabs (All / New / Original / Gear / Modes & wins / Other new / Combat) and the
  "New only" box: no longer needed. The search box and the status / sort selects remain; "Jump to new challenges" scrolls to the tabs.


## 2026.11.07.3 — 23:31

### Counted games, decided games, ping cap (user, 2026-11-07, Review DATA-2 / DATA-3 / DATA-5)
- **Averages, rates and win rates now count only games of 2+ minutes with 2+ players per team** (present for at least half of
  the game): profiles, trends, compare, the site-average ticks and the leaderboard. Games played, hours, emotes and payload push /
  block still count every match. Each ⓘ on a player's page says 'Counts N of M games'; the leaderboard and compare footnotes say
  the rule. Achievements keep their own rule (4+ minutes, 3+ per team). Stored per match (`counted_for_stats`); existing matches are
  classified once at the first start (about a second).
- **'Decided' games are shown:** the win-rate ⓘ says how many games have a recorded winner (43 % of the archive has none), the
  home 'Capture point wins' card says 'of N decided'.
- **Ping spikes capped:** readings above 400 ms count as 400 in profile / leaderboard / trend averages (the match page keeps the
  raw average). Stats version 11: replays are read again in the background, old averages stay until each one is done (no data
  disappears; the cap applies to a player once their replays are re-read).
- **Discord staff ids checked at startup (SEC-2):** an id in `ECHOVR_DISCORD_PREVIEW_ROLES` that is neither a role nor a member of
  the server is logged as a warning (a typo would otherwise grant the Console to nobody, or to a stranger who joins later).
- Discord accounts that do not exist are remembered for an hour instead of being asked again every 30 s (PERF-6).
- **After updating:** nothing to do. The NAS re-reads the archive in the background (hours at 2 workers); the site stays up.


## 2026.11.07.2 — 23:13

### Fixes from the 2026-11-07 review (docs/Review-2026-11-07.MD)
- **A busy database no longer loses work (BUG-1, BUG-3):** writers wait up to 30 s for each other instead of failing after 5 s with
  `database is locked`; if it still happens, the replay goes back into the queue (its old match stays) and a combat report is read
  again on the next scan. Before, the replay was marked failed, its match deleted, and the report stuck as failed.
- **New: "Forget replays whose file is gone" (BUG-2)** in the Console (Replays tab) and `admin.bat forget-missing`: after the replay
  folder was moved or files were deleted, the rows (and matches) whose file is no longer under the folder are forgotten; players
  stay and the same matches recorded under another path keep showing. It refuses while the folder is offline.
- **Remote processing race fixed (BUG-5):** the server checks the "process on another PC" setting in the same transaction as it
  claims replays, and never takes back a claim the PC made after that check. The flaky test passes every time now.
- **Errors in one shape (BUG-4, BUG-9):** validation errors answer `{error_code: "bad_request", message}` (the pages show the message
  instead of "Request failed (422)"); an id beyond 64 bits is 404, not a 500.
- **Match page (BUG-6, BUG-7):** an unknown `?tab=` shows the players instead of an empty page; the Combat report is asked for only
  when the match has one (`has_combat` on the match answer), so no more 404s in the browser console.
- **Console (SEC-3):** the Arena card shows the first line of an error only, never the SQL statement.
- **Combat lists (GUI-7):** reports with 0 players (empty lobbies) are left out (`min_players`, default 1).
- **GUI, approved one by one (GUI-1, 2, 4, 5, 9, 10, SEC-5):** the top bar shows the name (a link to My profile) and Log out; the home
  'Players seen in Combat' card opens on 7 days; on phones the Recent matches table becomes cards, tab strips scroll with a fade
  hint, the leaderboard shows one line per player (tap for the rest) and the match highlight cards sit two per row; achievement
  tiles say 'nobody yet' / 'under 1 % of players' instead of '0 %'; the Twitch player on the home page loads only when clicked
  (a poster says Live now / Offline), so no third-party scripts run by default. On laptop widths (up to 1500 px) the
  "Processing N replays" indicator is the spinner alone (text on hover), so the top bar stays one row while an import runs.
- GitHub Actions now runs `pip-audit` and `npm audit` (advisory, not blocking). `config.py` escape-sequence warning fixed.
- Nothing to do after updating; no replay is re-read.


## 2026.11.07.1 — 22:31

### End-to-end review and reference files (user, 2026-11-07)
- **No change for people using the site.** The whole app was tested end to end (414 backend tests, build, every API route, every page in a
  headless browser at desktop and phone width, console commands, permissions, icons, caching, load). Findings and the options for
  fixing them are in `docs/Review-2026-11-07.MD` (BUG / SEC / PERF / GUI / DATA numbers): the main ones are SQLite `database is locked`
  at startup losing a replay result and combat reports (BUG-1), and a changed replay root duplicating every replay row (BUG-2).
- **Reference files for future edits:** `docs/reference/` now holds code maps that are read instead of the source (`README.md` explains
  them): generated `SYMBOLS.md`, `API-ROUTES.md`, `FRONTEND-MAP.md`, `CSS-MAP.md`, `TESTS-MAP.md` (`python app/tools/reference/make_reference.py`,
  run after each change set) and hand-written `CODE-MAP.md`, `RECIPES.md`, `E2E-TESTING.md`.
- **Repeatable local end-to-end run:** `app/tools/e2e/run_local.bat` starts the site with the Discord login bypassed (fake secrets, a test
  id with Console access, rate limit off), `local_login.py` mints the session cookie, `api_sweep.py` and `browser_sweep.py` run the checks.
- `.gitignore` and `upload_to_github.bat` now exclude only the old-site material in `docs/reference/` (minimaps, extract, gear table),
  so the code maps are uploaded with the app.

## 2026.11.06.24 — 22:50

- **Reverted:** the gear groups (Weapons, Tac mods, Ordnances) and the pink catalogue icons are gone again. The pink-purple lock emblem on locked challenges stays.

## 2026.11.06.23 — 22:46

- Version bump only: no changes for people using the site.

## 2026.11.06.22 — 22:45

- **Gear challenges grouped:** in In one Game, Day, Week and Cumulative, the weapon, tac mod and ordnance challenges now sit together in three labelled, colour-framed groups (Weapons, Tac mods, Ordnances) below the others.

## 2026.11.06.21 — 22:41

- Version bump only: no changes for people using the site.

## 2026.11.06.20 — 22:40

- **The pink lock is never greyed:** the lock emblem on locked challenges keeps its colour and full strength.

## 2026.11.06.19 — 22:38

- **Challenge catalogue icons are pink-purple:** with no player selected the icons use the original lock colour instead of white.

## 2026.11.06.18 — 22:35

- **Lock emblem is pink-purple again:** locked challenges (below the first medal) show the original pink-purple lock instead of the grey one.

## 2026.11.06.17 — 22:22

- **Challenge tiles are shorter:** the rule text is gone from the challenge grid tiles; hover a tile to see it.

## 2026.11.06.16 — 18:48
- The payload-blocking achievement "Wall of Steel" is now called "Immovable Object" (same id, tiers and progress).

## 2026.11.06.15 — 16:47

- **Known issues button removed again:** the "Known issues" button and page added earlier in this release are gone; nothing else changed.

## 2026.11.06.14 — 16:11

- **Achievements page:** fixed the stripe of card edges showing under the "Top players" and "Recent medals" cards, and evened out the line spacing of the name / medal chip / challenge text in the medal cards.

## 2026.11.06.13 — 16:03

- **Both Hands, easier rule:** now "Switch your arm setting between games: in any 7 days, play this many games with your left arm AND this many with your right arm", with targets like "3 games each". The standing-still check is gone; a game still needs 4+ minutes, 1+ minute in bounds, 3+ players per team and 90 %+ of it on that arm.

## 2026.11.06.11 — 15:21

- **New achievement, Both Hands (Movement):** play full games with the left arm and with the right arm in any 7 days; the arm with fewer games counts. Medals at 1 / 3 / 5 / 8 games on each arm. Open to every player (the arm is a game setting). A game counts with 90 %+ of it on that arm, 4+ minutes, 1+ minute in bounds, 3+ players per team and not standing still for more than half of it (no AFK / join-and-leave); a win is not needed. The replay challenges go from 157 to 158.

## 2026.11.06.10 — 14:36

- **Achievements page:** "Top players" and "Recent medals" now sit side by side, 50:50, to save space. Each shows only as many cards as fit its half (no sideways scrolling); on narrow screens they stack.

## 2026.11.06.9 — 14:26

- **Recent medals:** the player name and "earned" now sit on the same line.
- **Mega Prizes:** the prize pictures are slightly bigger.

## 2026.11.06.8 — 12:57

- **Player goals:** a player's page now lists five goals (was three).

## 2026.11.06.7 — 12:51

- **Recent medals:** fixed the broken card layout from 2026.11.06.5 (text squeezed into a narrow column beside the coloured icon).

## 2026.11.06.6 — 12:47

- **Achievement icons without a player:** in the catalogue (no progress shown) every icon is now one neutral colour instead of its original art colours (red hands, white skulls ...); with a player they still take the colour of the tier reached. Uploaded icons keep their own colours.

## 2026.11.06.5 — 12:42

- **Recent medals:** each medal's icon now takes the colour of the tier earned (bronze, gold, platinum, crown gold-to-pink), like the badge cards, instead of plain white. Uploaded icons keep their own colours.

## 2026.11.06.4 — 12:38

- **Mega Prizes:** the pane is shorter (smaller photos, tighter spacing, photos beside the text on wide screens) and the "Search a player" box is removed from both prize cards; each shows its top list.
- Also includes everything listed under 2026.11.06.3 just below.

## 2026.11.06.3 — 12:25

- **Achievements:** "In one Game" is a tab of its own again (In one Game, Day, Week, Cumulative); the "One game" chip inside Day is gone.
- **Player pictures:** a player's page now shows the Discord picture of the account seen with them on the match list (as the list pages already did), not only bot-linked or exact-name matches.
- **Discord limits:** fresh picture lookups are capped at 20 per minute for all visitors together, a 429 from Discord pauses them for its Retry-After time, and the last known picture is kept meanwhile.
- **Player goals:** the goals on a player's page now lean towards what that player already plays (modes, gear, movement ...): themes they are busy with count as easier, so the three goals fit their style.
- **Pictures on lists:** Players, Leaderboard, Combat and Achievements lists now also match players to Discord members by exact name (as the player page does) and ask Discord for members missing from the server list, within the request budget; a thin answer is kept for 20 s instead of 5 min while the member list is still loading.
- **Home:** "Live on Twitch" now heads the video and "Latest matches" (with "All matches") heads the list beside it.

## 2026.11.06.2 — 12:15

- Version bump only: the release is everything listed under 2026.11.06.1 just below; nothing else changed.

## 2026.11.06.1 — 11:36

### Four medals instead of five (user, 2026-11-06)
- **Bronze, gold, platinum and a crown** (a gold crown with a pink diamond = completed). Silver is gone; every ladder keeps its range:
  bronze = the old first target, gold = the old gold, platinum = the old diamond, crown = the old platinum. Medal Collector, the Combat
  challenges and the Echo Combat Veteran ladder follow (Medal Collector 5 / 25 / 65 / 98; Echo Combat Veteran 33 / 333 / 600 / 1000).
- **Progress is 25 % per medal** (was 20 %). **Anyone who held silver is now at bronze** until they reach gold; platinum and the crown
  keep their old targets. Medals are computed on request, so nothing needs migrating.
- The medal frames were recoloured to the exact medal colours, so the icon, frame, name and bar match; the crown's icon and name are
  a gold-to-pink gradient, and the lock emblem on unmedalled challenges is neutral grey (it was magenta).

### Achievements page (user, 2026-11-06)
- **Three pages:** Day, Week and Cumulative; the single-game challenges sit in Day behind a "One game" chip (the old theme tabs are filter chips inside each page, plus a "New" chip). Each
  challenge is a compact tile with its icon, name, a short description and a percentage (your progress, or the share of players who
  unlocked it). Everything else (targets, rules, rarity) is in a card on hover or tap; a card opened with a click has a small cross.
- **Rules** moved to the bottom of the page and say that nothing is locked behind another challenge.
- **"Test Drive:" prefix removed:** the 19 challenges are named like "Pulsar (weapon)", "Detonator (ordnance)", "Repair Matrix (tac mod)".
- **Renamed:** Silicon Assassin is now Comet Commandments.
- **Mega Prizes:** front and back pictures of each prize (zoomed, drag or scroll them up and down); a player search inside each prize
  card instead of one at the top; a top-10 list that shows 3 players and scrolls for the rest, with ▲▼ for places gained or lost in the
  last 24 hours and the matches gained.
- **Echo Combat Mega Prize now includes the replay files:** matches from the replay files are added for players linked to their Nakama
  account by Discord ID, only for matches before the live count started (so nothing is counted twice), with the same rules (4+ minutes,
  3+ players per team, public, inside the Mega Prize period). It only counts inside the period, so check its start date in the Console.

### Player page and menu (user, 2026-11-06)
- **Achievements strip** above the Today / This week / This month / All time filters: average progress, crowns and medals, and the three
  challenges closest to their next medal.
- **Removed** "Games per map" and "Favourite map". The "Combat" tab is now **Recorder stats** (separate data from the replay stats).
- **Combat moved into Leaderboard** as a second board (Replay stats / Combat stats); the old /combat address still works. "My profile" sits
  next to Log out.
- **Heatmap:** softer colours (no neon cyan), teams are mixed where they overlap instead of one hiding the other, zoom up to 24x with the
  + / − buttons (drag to pan), and zoomed lines are smoothed.

### Added later the same day (user, 2026-11-06)
- **Your goals (player page):** three personal goals above the stats, picked at random but always from that player's EASIEST next medals,
  so they start small and get harder as the player completes them. Reaching a medal replaces its goal with another. Nothing is stored:
  the pick is a hash of player + challenge + medal level, so it is stable until something is completed and different for every player.
  A big "All achievements" button leads to the full list. The strip's bar is split by best medal (crowns first, in the crown colour).
- **Discord pictures** beside names on Players, Leaderboard (both boards and the podium) and Achievements (top players, recent medals).
  They come from the Discord server's member list the site already reads, so a list page makes no Discord request per row; a player who
  switches their picture off in their profile disappears at once (the lookup is its own request, never part of the cached lists). Players
  without one get a letter. **Players list** also shows hours played and favourite map (no win / loss figures: those can be hidden).
- **Console:** the Mega Prize period has **Visible to** (Preview role only is the default, as before; everyone from the start date;
  nobody). The launch / challenge / Mega Prize forms no longer lose what you typed: a slow answer from the server could overwrite it, and
  a refused save wiped the form.
- **Achievements page:** tiles are wider (names fit on every screen), every medalled icon takes its medal colour (the 28 challenges with
  no icon of their own were left white), the Mega Prize pictures fit the window with + / − buttons and drag in any direction.
- **Home:** the big player search is gone (the one in the menu stays). The Day tab now holds the single-game challenges behind a "One game" chip.

### Tested (2026-11-06)
- 414 backend tests, all 60 GET routes against a snapshot of the real database (no errors, none over 3 s), and about 90 browser checks.
- **Known flaky test:** `test_remote.py::test_damaged_track_files_are_left_out_not_saved` failed once in five full runs and passes alone;
  it looks timing-related. Ignore it unless it fails again.
- Not tested: a real Discord login, real Mega Prize data, and a real phone.

## 2026.11.05.5 — 21:35

### Mega Prizes (user, 2026-11-05)
- **Own Start-End dates:** Console, Achievements tab, "Mega Prize period" (`admin.bat mega-period`). Only Combat and Public Arena matches inside them count towards the prizes; the achievements keep their own launch date and challenge period. With no start date of its own the Mega Prize period follows the challenge period, so nothing changes until you set one. The Mega Prizes tab shows these dates, and the Console dashboard has a Mega Prizes card.
- **1000 matches** for both prizes (was 750). Echo Combat Veteran medals: 33 / 133 / 333 / 600 / 1000 (was 25 / 100 / 250 / 450 / 750).
- **Renamed:** Delta-13 from Lone Echo 2 (was Delta Squad BioMass Chassis) and Jack Series 11 from Lone Echo 1/2 (was OG High Quality Jack Model).
- **Wording:** "No winners yet / N winners so far: everyone who reaches 1000 wins the prize." and "Closest to winning (not there yet)", so it is clear there can be many winners.
- **Live dot:** both prize cards show a pulsing green "Recording live data" while the Mega Prize period is running.

### Pew Pew Proof is a ladder, Gearhead is easier (user, 2026-11-05)
- **Pew Pew Proof:** now 4 / 6 / 10 / 15 / 25 games in a row (4+ minutes, 3+ players per team) that average fewer than 5 deaths per game, within any 7 days and on at least 3 different days (was one step: 25+ games in a week). Of the 843 players with 20+ counted games, 20 / 15 / 8.5 / 3.8 / 1.3 % reach these; the old single step was reached by 14 players in the whole archive.
- **Gearhead:** 5 / 10 / 15 / 20 / 25 games in a row on one loadout (was 4 / 8 / 15 / 39 / 65; platinum was reached by 0.5 % of those players, now about 5 %: 41 / 19 / 11 / 7 / 5 %). Only games of 4+ minutes with 3+ players per team count, a short game neither extends nor breaks a run, and a game with no loadout data is skipped. A game with no single main loadout still ends the run.

### "Only X in any 7 days" gear challenges need 3 different days from gold
- **All 19 weekly gear challenges** (Pulse Check, Eat My Nova!, Throws Better Than an Arena Disc ... Ghost in the Shell, the new-gear ones and Charged Up, Blazar Barrage, Dot Matrix): bronze and silver (1 and 4 games) count as before. Gold, diamond and platinum (6 / 9 / 13 games) need those games on at least 3 different days inside the same 7 days, so one evening can no longer fill the week. Without the 3 days the count stops at silver.
- On the full archive this lowers 1,418 of 5,005 gold-or-better medals (832 players), mostly gold to silver. Medals are computed on request, so nothing needs migrating.
- The card note reads "Gold+: 3+ different days". The other 7-day challenges are unchanged (the four map ladders would lose about 3-5 % of their gold-or-better; left as is).

## 2026.11.05.4 — 20:33

### Duplicate achievements removed
- **Frequent Flyer:** it was the same as King/Queen of Pubs, since every recorded game is a pub.
- **Starburst Beta Tester, Protostar Prototype, Quantum of Quark, Blazar of Glory, Now You See Me, Connect the Dots:** they counted the same games as the Starburst, Protostar, Quark, Blazar, Translocator and Dot Field Veterans.
- The replay challenges go from 164 to 157. Nothing else changes, but "completed" and Medal Collector totals are out of the new number.

### Three new Combat achievements
- **Siege Breaker** (objective damage in one game), **Field Medic** (heal bubbles in one game) and **Shock Trooper** (stuns in one game), from the recorder's match reports only. Like the other Combat achievements they are provisional and stay out of the totals. Field Medic and Shock Trooper only count matches with a complete event log.

### Impossible top medals fixed
Nobody had ever reached these platinums. All targets now sit within what players have done:
- **Roboticide** 6 / 8 / 9 / 11 / 14 %. **Cyberkinetic Enhancements** 2.6 / 2.8 / 3 / 3.2 / 3.5 m/s. **Point Guard** 2 / 3 / 3.5 / 4 / 4.5 min.
- **Loadout Roulette** 2 / 3 / 4 / 5 / 6. **Mime Troupe** 2 / 4 / 6 / 8 / 10. **Showboat** 4 / 6 / 8 / 10 / 14. **Dance Floor Legend** 20 / 40 / 60 / 80 / 120.

### Fixed
- Medal text says "Play 1 game", not "Play 1 games".

### Times are in your own timezone
- **Every match, player and release time and date** now shows on your own clock. Hover a match time to see your timezone and the UK time.
- **Fixed:** "Last match … ago" on the home page was hours out for anyone outside the UK.
- **Days stay on one clock:** achievement days, challenge dates, "Today", "This week", charts and the match date filter use UK days, so everyone is counted the same. The footer and the achievement rules say so.

### Console: tabs instead of a long menu
- **Six tabs:** Dashboard, Players, Replays, Achievements, Audit log and Permissions. The 21-button menu is gone and Permissions is no longer stacked under everything.
- **Status first, risky actions apart:** Replays opens on a short import progress panel with its actions right below (the long status page opens with "Show full status"). "Re-process every replay" sits alone in a red danger area.
- **Fix a replay:** Re-process, Repair and Aggressive repair of one replay are now one form with a Strength choice.
- **A refresh keeps your place:** the tab and command are in the address, so they can be linked to too. "Find a command" still finds everything, from any tab.
- **Dashboard:** a new Arena counter card shows at once whether the counter is working (it was inside the slow winners report). The Achievements card says "Preview only" instead of "Coming soon" when that is the setting.
- **Mega Prize winners** has its own button, away from the 179-row export, and only loads when you open it.
- The commands, permissions and audit log work as before.

### Map and mode challenges easier at the top
The top medals were far above what anyone plays. Bronze and silver stay the same.

**In one day**
- **Bird of Prey, Constant Contesting, Techneium-99, Blast Furnace:** 3 / 4 / 5 / 7 / 9 games (was 3 / 4 / 6 / 10 / 13). Since 1 August 5 or 6 players reach platinum on each map (before: 0 or 1).
- **Point Captured:** 5 / 7 / 9 / 12 / 16 (was 5 / 7 / 9 / 16 / 22). Since 1 August 6 players reach platinum (before: 3).
- **Checkpoint Reached:** 5 / 7 / 9 / 12 / 16, the same as Point Captured (was 5 / 7 / 9 / 16 / 22). Since 1 August 5 players reach platinum (before: 1).
- **Combat on Quest When?:** 9 / 13 / 18 / 24 / 30 (was 9 / 13 / 18 / 31 / 42). Since 1 August 6 players reach platinum (before: 1).

**In any 7 days**
- **Frame-Drop Hell, I've Got a Fever, Phoeniconaias minor, Phoenicopterus ruber:** 4 / 6 / 8 / 12 / 18 games (was 4 / 6 / 8 / 23 / 44). Since 1 August 4 to 6 players reach platinum on each map (before: none).
- **I'd Rather Be on Kronos II, Sakura's Dancing Flamingo:** 10 / 18 / 25 / 33 / 40 (was 10 / 18 / 25 / 52 / 65). Since 1 August 4 players reach platinum on each (before: none).
- **Who Do I Have to Pew Pew Pew to Get a Combat Update Around Here?:** 15 / 30 / 50 / 65 / 80 (was 15 / 30 / 60 / 130 / 195). Nobody had ever reached the old platinum; since 1 August 5 players reach the new one.

- **Do:** restart the backend. No re-read is needed.

## 2026.11.05.3 — 19:13

### Lone Wolf harder
- **Farther away:** you now have to stay more than 3.5 m from your teammates (was 2.6 m). The other "near a teammate" stats and challenges keep 2.6 m.
- **Time on the map:** a game needs at least 1 minute counted in bounds. 25 of the 39 platinum games since 1 August had less. The targets stay 94.6 / 96.4 / 98.2 / 99.1 / 100 %.
- **Who reaches them:** since 1 August about 30 / 19 / 10 / 6 / 3 % of players reach bronze / silver / gold / diamond / platinum (before: 56 / 39 / 25 / 17 / 13 %).
- **Medals:** players may drop a medal or more until they earn it again under the new rule.

### Untouchable is one medal and needs time on the map
- A win without dying now needs at least 1 minute counted in bounds. 122 of the 134 wins that qualified before had none at all, so no death could be recorded. Holders drop from 85 to 9.
- It is one medal now instead of a ladder: nobody has more than 2 such wins, so the old 8 and 13 targets could not be reached.

### I'ɯ ꓭɐʇ ꓭoʇ: a real week
- The 7 days now need games on any 3 different days and at least 10 minutes counted in bounds in total. The targets stay 9.3 / 22 / 36 / 47 / 57 %. Since 1 August 21 / 8 / 6 / 4 / 3 of 592 active players reach them.

### Console: is the Arena counter working?
- The *Mega Prize winners* panel now has an **Arena counter** line: working or failing, when the match list was last read, public matches and players on it, how many were counted since the last restart, and the last error.

### Speed Demon: real games only, new top targets
- A game now needs at least 1 minute counted in bounds. All 20 platinum games had less, all on Fission.
- **Targets:** 3.5 / 4 / 4.5 / 5.25 / 6 m/s (was 3.5 / 4 / 4.5 / 7.2 / 9.1): with the limit nobody could reach the old platinum. About 88 players in the archive reach the new diamond and 25 the new platinum.

### The Wings of RAD_Wyvern: a real week, new targets
- The 7 days now need games on any 3 different days and at least 10 minutes counted in bounds in total. All 16 platinum windows had under 5 minutes, most of them one game.
- **Targets:** 2.75 / 3 / 3.25 / 3.5 / 3.75 m/s (was 3.5 / 4 / 4.5 / 6.5 / 7.8). Since 1 August 65 / 41 / 20 / 5 / 1 of 592 active players reach them, and 42 players in the archive reach platinum.

### Hug Your Frenemy: a real week, new targets
- The 7 days now need games on any 3 different days and at least 10 minutes counted in bounds in total. 84 % of the windows that reached platinum had under 5 minutes.
- **Targets:** 12 / 14 / 16 / 18 / 20 % (was 18 / 24 / 28 / 33 / 40). Since 1 August 34 / 17 / 4 / 2 / 2 of 592 active players reach them, and 40 players in the archive reach platinum.

### Can We Talk About This?: real games only, new targets
- A game now needs at least 1 minute counted in bounds. 76 % of the games at platinum level had less.
- **Targets:** 25 / 30 / 35 / 40 / 50 % (was 26 / 34 / 42 / 51 / 60). About 56 / 34 / 18 / 10 / 4 % of regulars reach them, and 66 players in the archive reach platinum.

### Tech Support w/RAD_Natalie: a real week, new targets
- The 7 days now need games on any 3 different days and at least 10 minutes counted in bounds in total. 81 % of the windows that reached platinum had under 5 minutes.
- **Targets:** 16 / 20 / 24 / 26 / 28 % (was 32 / 42 / 49 / 53 / 58). Since 1 August 48 / 25 / 8 / 4 / 1 of 592 active players reach them, and 163 players in the archive reach platinum.

### Statue: real games only, harder
- A game now needs at least 1 minute counted in bounds. 36 % of the games at platinum level had less.
- **Targets:** 54 / 61 / 67 / 73 / 80 % (was 45 / 54 / 61 / 67 / 73). About 68 / 42 / 25 / 12 / 6 % of regulars reach them, and 63 players in the archive reach platinum.

### Full Team Salvo: real games only
- A game now needs at least 1 minute counted in bounds. 24 % of the games at platinum level had less. The targets stay 50 / 61 / 69 / 74 / 81 %.

### After updating
- **Do:** recreate the container, at a quiet time and with the remote worker on (update that PC first: it must have the same version). `STATS_VERSION` 10 reads every replay (~29.5k) again: this takes hours, and the "Processing N replays" counter shows how many are left.
- **During the re-read:** match stats stay up. Lone Wolf has no value for a replay until it has been read again, so its medals fill in as the counter goes down; no medal is given by mistake. Other achievements change at once when the backend restarts.


## 2026.11.05.2 — 18:03

### Fixes from the full website test
- **Pages no longer jump while loading.** The "Log in with Discord" button keeps its place from the start and now fits on the header's one line from 1280 px wide (below that the menu has its own row). The loading placeholders on player and match pages and the text on the Combat page no longer move the page either. Up to 1380 px wide the menu hides the "Coming soon" tag beside Achievements; the page itself still says it.
- **Compare:** after picking one player the page now shows who you picked (with a × to remove them) and asks for one more, also when you arrive from a player page. Large numbers have thousands separators, and a player with no data shows "–" instead of "– m/s".
- **Phones:** the Playback tab no longer scrolls sideways, an opened tab is scrolled into view in the tab strip, and the Players list shows games and last seen without scrolling sideways.
- **Addresses that lead nowhere** (`/matches/abc`, an unknown player or combat match) show a clear "not found" message with links, instead of "Match #NaN" or "Request failed (422)".
- **Combat table:** the chosen stat no longer appears in two columns.
- **Matches:** the "Match type" filter is gone. The recorder skips private matches, so "Private" could only ever show 0.
- **Combat stats are no longer labelled "beta".** On a player page the "Beta Data Collection" tab is now "Combat" (old `?tab=beta` links still open it), and the match page's Combat tab drops the label too.
- **Behind the scenes:** leaving the Playback or Heatmap tab no longer logs an error in the browser console.

Nothing to do after updating; no re-read is needed.

## 2026.11.05.1 — 16:03

### New Combat challenges
- **New Combat section** with 15 challenges from the game's own counters. In one game: Frag Out (kills), Wingbot (assists), Heavy Hitter (damage), Net Positive (kills minus deaths), Objective Threat (objective eliminations), On the Objective (objective time), Flawless (10+ kills, no deaths). In one day: Kill Spree, Busy Hands. All time: Body Count, Force Multiplier, Demolition Crew, Top Fragger, Triple Threat, Selfless.
- **Assists need more than kills** at every medal.
- **What counts:** games of 4+ minutes with 3+ players per team, judged from the recorder's match reports alone, so from 4 November 2026 on. They are completely separate from the replay stats and share only the Achievements page, so a report with no replay counts too.
- **Provisional:** the targets come from about one day of reports and will be re-tuned as data comes in. These challenges earn medals but stay out of average progress, completed and medal totals, the achievements ranking and Medal Collector.

### Test Drive challenges
- **19 new challenges under In one game,** one per weapon, tac mod and ordnance: use it for at least 3 minutes in one game with 3+ players per team. Time is the item's share of the game x time played, so waiting to respawn with it equipped counts. These use replay data and count toward the totals, but not toward Medal Collector.

### Showboat and close medals
- **Showboat:** the old Showboat (emotes in any game) is gone. Victory Lap (emotes in a game your team wins) is now called Showboat; its targets and everyone's progress on it stay the same.
- **Player achievements:** the separate "Close to a medal" row is gone. Cards in each section's list are highlighted instead once they are at least a quarter of the way to the next medal, from yellow to green as they get closer. Hover a card to see how far along it is.
- **Do:** restart the backend and rebuild the website (run.bat). Every player is evaluated again once, because the rules changed.

## 2026.11.04.11 — 19:52

### Beta Data Collection: combat stats
- **New data source:** the recorder's match reports (`matches\*.json`) are collected like the replays: read-only folder, a scanner checks it about every minute, new and changed reports are read by themselves. It is completely separate from the replay data (own tables, own reader, own pages); numbers can differ from the replay stats.
- **Player profile:** new "Beta Data Collection" section (above Recent matches) with kills, deaths, assists, eliminations, damage, objective damage / time, K/D, kills and damage per minute, per-map table, and, for matches with an event log, shots, kills / deaths / shots by weapon, tac mod uses, heal bubbles, stuns and self-kills.
- **Match page:** a "Combat stats" block on the Players tab, right under the players (no beta label: these are the game's own exact counters), with the combat scoreboard of that match (only when a report exists for it).
- **Combat page** (`/combat`, new in the top bar): leaderboard by stat, period, map and minimum matches, and the latest combat matches; `/combat/<match id>` for one match.
- **Not shown:** damage taken (spectators do not get it). Shots and weapon numbers exist only for matches with an event log.
- **Do:** recreate the container (docker-compose now sets `ECHOVR_COMBAT_SOURCE: /replays`). Nothing to re-read: the replay data is untouched. See CombatStats.MD.

## 2026.11.04.10 — 14:27

### Challenges eased, units shown, 3+ players per team
- **On a Roll:** win 2 / 3 / 4 / 7 / 8 games in a row (was 2 / 4 / 6 / 13 / 18).
- **Grand Tour:** win on all 4 maps 1 / 3 / 6 / 16 / 26 times (was 1 / 4 / 10 / 39 / 117).
- **Payload, now in plain units:** Pedal to the Metal (longest push in one game) 40 / 70 / 100 / 150 / 200 **seconds**; Immovable Object (longest block in one game) 15 / 30 / 45 / 62 / 81 **seconds**; Freight Train (total push time) 5 / 12 / 25 / 46 / 70 **minutes**. Hold the Line is unchanged (its description now says what a defence win is).
- **Units on the tier steps:** the targets under each progress bar now include the unit (m/s, s, min, %).
- **3+ players per team:** win challenges (Centurion, On a Roll, Hot Day, Grand Tour, Point Taker, Cargo Hauler, Clean Sweep, Special Delivery, Hold the Line) and the Payload time challenges count only games where both teams had at least 3 players for half the match (3v3, 3v4, 4v4, 5v5 ... all count; against cheating). The one-game challenges that needed a 4v4 now accept 3v3 and up. Shown as "3+ players per team" on each card.
- **Do:** restart the backend. Totals for some players will drop where their wins came from small games.

## 2026.11.04.9 — 14:10

### Gear Veteran challenges retuned
- **All 18 gear Veterans (every weapon, ordnance and tac mod, plus Overclocked):** bronze / silver / gold / diamond / platinum are now 9 / 26 / 87 / 115 / 150 games (were 8 / 24 / 79 / 318 / 674). Bronze to gold are about 32 % above the previous base; diamond and platinum were lowered so that completing every gear Veteran is possible: all 18 platinums need about 1,200 weapon games (8 weapons x 150).
- **Do:** restart the backend (progress is computed on request, so levels change at once).

## 2026.11.04.8 — 13:06

### Achievements page
- **Removed:** the intro line "The original ECRanked achievements plus new ones…" above the player search.


## 2026.11.04.7 — 13:04

### Mega Prizes: finishers only, no spectators
- **Arena card:** the list under Play 750 Public Arena Matches shows only players who reached 750, not the top 5 by progress. Searching a player still shows their bar.
- **Spectators and moderators:** they are not counted, and anyone seen as a spectator or moderator in a public match loses their stored Arena count (the match list's `team` field). Records are cleared the next time they appear in the list.
- **Do:** restart the backend.


## 2026.11.04.6 — 12:54
### Mega Prize pictures show again
- **Fixed:** the Delta Squad BioMass Chassis and Jack pictures on the Mega Prizes tab appeared as broken images. The pictures are loaded with the site header and shown from memory (`blob:`), which the browser protection (Content-Security-Policy `img-src`) did not allow. It now does; nothing external was opened up.
- **Do:** restart the backend, then hard-refresh the page (browsers cache the old protection header).


## 2026.11.04.5 — 12:47
### Super Ultra Hyper Turbo easier
- **Targets:** top speed in one game 14 / 17 / 20 / 26 / 30 m/s (was 14 / 18 / 22 / 35 / 42). From the archive about 12 % of players reach gold, 1.4 % diamond and 0.3 % platinum (before: 0.1 % and 0.0 %).


## 2026.11.04.4 — 12:46
### Lone Wolf 15 % harder
- **Targets:** the distance to 100 % shrank by 15 %: 93.2 / 95.8 / 97.5 / 98.7 / 99.6 % of a game away from teammates (was 92 / 95 / 97 / 98.5 / 99.5). Diamond and platinum are still 30 % further up.


## 2026.11.04.3 — 12:43
### Easiest challenges made a little harder
- **Gear (all weapons, ordnances, tac mods, new gear included):** veteran ladders 6 / 17 / 55 / 170 / 400 games, "only X in one day" 3 / 6 / 9 / 13 / 17, "only X in any 7 days" 6 / 12 / 18 / 35 / 55 (diamond and platinum are still 30 % higher, all-time still +20 %). They stay identical for every item.
- **Others:** Capture Point / Payload games in a day 5 / 7 / 9 / 12 / 17, Combat pubs in a day 9 / 13 / 18 / 24 / 32, map games in any 7 days top steps 18 / 34, Centurion top step 300, Hot Day top step 18.
- **Medals:** players near a step may drop one medal until they play more.


## 2026.11.04.2 — 12:39
### Challenge descriptions in plain language
- **Reworded:** about 50 challenge descriptions now read as plain instructions ("Share of one game spent close to a teammate", "Use all 4 weapons (...) in one game", "Win games on all 4 maps", ...). Maps read "Play games on Dyson" instead of "of Dyson".
- **Unchanged:** targets, counting rules and medals. The small tags under each challenge (best game, 4v4 only, ...) are as before.

## 2026.11.04.1 — 10:58
### Console form remembers its settings
- **Launch date and challenge period:** the form now opens with the saved start date, end date and "Visible to" instead of empty. They were
  always kept in the database (so they survive closing the Console and restarting the server); the form just did not show them.

### Layout
- **Mega Prizes is the first thing on the Achievements page** (Preview role only).
- **Achievements page, easier to read:** a sticky jump bar (one button per section with its count, plus Expand all / Collapse all); a
  toolbar that filters (text, status, new only) and sorts (closest to the next medal, rarest first, A to Z) every section at once;
  sections start folded with their challenge count; a *Close to a medal* row above *Not yet started* on a player's page; the five medal
  targets as coloured dots on every card; and the rule notes and rarity moved into a *Details* fold on each card.
- **The medal progress bar is on every challenge card again** (empty, with its five targets, in the list of all challenges; filled in on a
  player's page). The coloured dots are gone.
- **"Use" an item now needs 10% of the game (was 5%)**: using a different weapon, ordnance or tac mod only counts once it was equipped for 10%
  of the match (affects Jack of All Trades, the gear challenges and Loadout Roulette). "Use only" stays at 90%.
- **"Use" and "Use only" explained better** in the Rules (and the card note): per slot (weapon, ordnance, tac mod), "use" = equipped for 5%+ of
  the game, "use only" = 90%+ (a short switch is fine; no rule changed).
- **Fewer sections:** *Experimental gear* and *Gear mastery* are one *Gear* section; *Wins*, *Payload* and *Capture Point* are one *Modes & wins*
  section; *Activity* is under *In one game* / *All time*. Six sections instead of ten (In one game 12, In one day 19, In any 7 days 25, All time 36, Gear 50, Modes & wins 17); nothing was removed.
- **Survival, Movement and Emotes are no longer separate sections either:** their one-game challenges are under *In one game*, their all-time
  ones (Untouchable, Dance Floor Legend) under *All time*.

### Layout
- **Achievements page, more compact:** a one-line intro, tighter Rules / Preview note / player search.
- **Mega Prizes layout:** the search results are one compact row per result (name, prize, bar, count) and the two prizes are matching
  cards with a picture, the prize and the rule (Arena also shows its top 5).
- **Echo Combat Mega Prize: games of 4+ minutes only** (like Arena), inside the challenge period.

### Security (Mega Prizes)
- **The Combat prize challenge is no longer in the public achievement list at all:** it used to be, which would have put it (and who
  completed it) in the public "recent medals", rankings and totals. It now lives apart and is only served to the Preview role.
- **Prize pictures are no longer public files:** they load through `/api/arena/image/...`, Preview role only.
- **Checked with the real login flow:** no login, a login without the role and a Preview-only login get nothing (the refusal says nothing
  about prizes); the winners report (it has Discord ids) is Console only; answers are never kept in a shared cache; no public answer
  mentions a prize or a winner. The winners CSV can no longer run a spreadsheet formula (names starting with = + - @), and the match list
  read is size-limited.

### Challenges
- **All-time count ladders raised by 20%** (to be reviewed): e.g. the Veteran ladders 5/15/50/195/455 → 6/18/60/234/546, Frequent Flyer, Loyal Bot,
  King of the Hill, the maps, Clean Sweep... The averages (% and m/s) and Medal Collector are not changed, and neither is the Mega Prize (750).
- **Mega Prizes: the progress bars are inside the cards.** Search a player and they show in the Combat and Arena card, one bar each; with no search the
  Arena card shows its top 5.
- **Removed "Unstoppable"** (win games in a row): "On a Roll" is the same challenge. 147 → 146 challenges.
- **Removed the 12 "Nothing but <item>" challenges** (one game using only an item): the daily "One with the <item>" ladders test the same thing. 159 → 147 challenges.
- **Shorter rule notes on every card**, on one line: "Best game · 4+ min games · 4v4 only · "Only" = 90%+ of the game" (was a long sentence per rule). Rarity stays in a small fold.

### Fixes
- **Mega Prize pictures were broken:** the scraper guard refuses `/api` requests without the site's header, which an image tag cannot send. The page now
  fetches the pictures itself with the header (the guard is unchanged; a test runs with it on).
- **The Rules box on Achievements is closed by default.**
- **Docker would not start** (`no such column: discord_id`): the Arena table made by the previous build lacked a column. Tables kept across
  rebuilds now get missing columns added at startup, with their data kept.

### Console
- **Permissions moved into the Console:** the Permissions tab is gone; the same panel is now at the bottom of the Console page
  (`/permissions` redirects there). Same access: the Console permission, and the server still checks every change.

### Mega Prizes
- **New challenge, Echo Combat Veteran:** play 750 Echo Combat matches (25 bronze, 100 silver, 250 gold, 450 diamond,
  750 platinum). Completing it earns the **Delta Squad BioMass Chassis** Mega Prize. Draft / beta: it is not in the
  normal sections, only in the Mega Prizes section of the Achievements page.
- **Arena counting (draft):** Public Echo Arena matches are now counted from the live Nakama match list
  (`g.echovrce.com/status/matches`), completely separate from the Combat stats (own tables and module, kept across rebuilds).
  Public Arena only (private matches and social lobbies are ignored); a match counts for a player once they have been in it
  for 4 minutes, once per match. Polling is very light: one small request a minute (`ECHOVR_ARENA_POLL_S`, 0 = off), backing off
  to 5 minutes when the list is unreachable.
- **Console report, Mega Prize winners:** the prizes are given out by hand, so the Console has a *Mega Prize winners* panel (Refresh, Copy,
  Download CSV): everyone who reached 750 inside the challenge period, with player id and Discord id. Combat counts the replay files,
  Public Arena the live match list. Arena needs 4+ minutes in the match (changed from 3).
- **Mega Prizes, now inside Achievements (Preview role only):** a *Mega Prizes* section at the bottom of the Achievements page (no separate tab; `/mega-prizes` redirects there; people without the role never see it) with a **search box**: type a player name and their progress
  toward each prize shows as a bar (Echo Combat games from the replay files; Public Arena matches from the match list), then the prize
  cards and the top 10 Arena players. **Progress starts at the set challenge period** (start date; end date if any): Arena counts nothing
  before it (and nothing at all while no start date is set), and Combat games before it are not counted.

## 2026.11.03.31 — 19:08
### GUI test fixes
- **Tab titles:** every page has its own browser-tab title ("davidyarker · Echo Combat Stats", "Surge #32779 · …").
- **Wide screens:** the home video is capped at about 900 px wide and tables at 1500 px, so names and numbers stay close.
- **Light theme:** darker medal shades so gold, silver and white names are readable on white.
- **Achievements, "Not yet started":** only challenges at least 5% of players have a medal for, shown once that share is loaded.
- **Phones:** taller tap targets for names and "Medal targets", and no text under 12 px in the medal bars and match rows.
- **Not found:** a missing match or page shows a message with links to Matches and Home.
- **Home heading:** "Echo Combat Stats".
- **Sneak peek:** the revealed examples now include two new 4v4 "In one game" challenges (Point Guard, Speed Demon), and a line shows how many "In one game" challenges there are.

## 2026.11.03.30 — 17:48
### Console: who sees achievements
- **Launch date and challenge period** has a **Visible to** choice: *Everyone* (public from the start date, as before), *Only
  people with the Preview role* (the start date is set and counts, but only Preview sees it; the public sees "Coming soon"),
  or *Nobody* (hidden from everyone, Preview included). It is saved at once; `admin.bat challenge --visible everyone|preview|hidden`
  does the same. Together with "Start today / End today" you can launch, hold back or hide again without touching the dates.

### Achievements page
- **Not yet started** replaces "Closest to your next medal": one scrolling row of 12 challenges the player has not touched,
  the ones most players unlock first (by the share of players with a medal) at the front, a bronze edge on each card.
- A start date that has already passed is no longer shown as "they start on …" on the Coming soon page.

## 2026.11.03.29 — 17:40
### Name
- The site is now called **Echo Combat Stats** (was EchoVR Replay Stats): browser tab title, top-bar name, the admin console
  and `run.bat` text. Internal names stay as they are (the `ECHOVR_*` settings, the `X-EchoVR` header, the container and
  database names), so nothing needs reconfiguring.

## 2026.11.03.28 — 17:36
### Layout
- **Full-width pages that adjust to the window**: the 1600 px limit is gone. The content fills the window, with side space
  that grows with the screen (16 px on a phone, up to 72 px on a very wide one) and the top bar lines up with it. Card grids
  and the sideways rows simply show more on a wider window; long paragraphs stay at a readable line length.

## 2026.11.03.27 — 17:29
### Fix: "Server busy · showing saved data" while replays are read
- `docker-compose.yml` now sets `ECHOVR_WORKERS: "2"` (was 4): the re-read of all replays (stats version 9) used every NAS core, and
  pages took 20-35 s, so the site showed "Server busy". Two workers read slower but leave the NAS to the visitors. **Needs the
  container recreated** with this compose file (or `ECHOVR_WORKERS=2` in the one the NAS uses); after the re-read is done it can go
  back to 4. Reading on the PC (Console > Where replays are processed) takes the load off the NAS altogether.

### Layout
- The page content can be up to **1600 px** wide (was 1320), so wide screens use more of the window and the sideways rows
  show more cards.

## 2026.11.03.26 — 17:22
### Console
- **The Status page is gone**: its live progress (replays read, how many are left, what is built from them, estimated time)
  is now **Status and import progress** in the Console's Processing group, and refreshes every 10 s while open. The "Status"
  link is gone from the top bar; an old `/status` link or bookmark opens the Console. Same data and the same access check
  (`/api/admin/status`).

## 2026.11.03.25 — 17:19
### Console
- **Fewer menus:** the Console menu has 5 groups instead of 8. Overview now holds Hide stats from players; Players holds the
  Discord access check; Repair holds the failed-replay tools.
- **Where replays are processed** is one form (this server only / another PC only / **both the PC and this server**)
  instead of three buttons. With *both*, the server and the PC each take different replays from the same queue, so a big
  re-read is done in roughly half the time. Also `admin.bat remote --both` and option 21 in the text menu.

## 2026.11.03.24 — 17:16
### Achievements page
- **Top players** is one line of cards that scrolls sideways. Each card shows the number of challenges **completed** (of
  147) instead of games, plus medals earned, how many are gold or better, the strongest section and the overall %. New
  endpoint `/api/leaderboard/achievers`; the full leaderboard is unchanged.

## 2026.11.03.23 — 17:07
### Achievements page
- **Recently completed** is one line of small cards that scrolls sideways (drag the scrollbar under it, Shift + wheel, or
  swipe) instead of a long list, so it no longer pushes the rest of the page down.

## 2026.11.03.22 — 16:39
### Fix: Discord login that fails without saying why
- When the Discord login fails, the address now ends `?login=failed&why=<reason>` (for example `state-mismatch`,
  `no-state-cookie`, `discord-400-invalid_client`, `discord-400-invalid_grant`, `timeout`) and the same reason is written
  to the server log ("Discord login failed: …"). The Achievements "Coming soon" page shows it too. Only a reason word;
  nothing secret. Nothing else about the login changed.

## 2026.11.03.21 — 16:24
### Console
- **Launch date and challenge period** has two new checks: **Start today (launches now)** and **End today**, so the dates
  can be set without typing them. Same permission as before (Console); nothing changes for other visitors.

### Challenges
- **In one day** is a little easier, from the replays of 28 Oct - 3 Nov (499 files; the play of 234 players with 3+ games).
  Gear "only X in a day" (all 12, plus the new gear, which shares the ladder): 3 / 5 / 8 / 16 / 20 (was 3 / 6 / 10 / 20 /
  26). Capture Point and Payload games: 4 / 6 / 8 / 13 / 20 (was 4 / 6 / 8 / 16 / 26). Games on one map: 3 / 4 / 6 / 10 / 13
  (was 3 / 5 / 7 / 13 / 18). Combat pubs: 8 / 12 / 16 / 29 / 38 (was 8 / 12 / 16 / 31 / 42). About 1 in 8 active players now
  reaches gold on the most-used gear in a day, 1 in 30 diamond, 1 in 80 platinum.
- **In any 7 days** was reviewed against the same games and left as it is: the week ladders already sit in the same range
  (diamond 1-2 %, platinum below 1 %) while the data covers only 4 busy days, so a full week will reach further.

## 2026.11.03.20 — 16:06
### Challenges
- **Combat on Quest When?** (Combat pubs in one day) is 20 % lower: 8 / 12 / 16 / 31 / 42 (was 10 / 15 / 20 / 39 / 52).

## 2026.11.03.19 — 16:03
### Achievements page
- Medal colours on the progress: each card in **Closest to your next medal** has a bottom edge in the colour of the medal
  it is heading for (bronze, silver, gold, diamond or platinum), and a section's progress bar takes the colour of its overall
  level (20 % bronze, 40 % silver, 60 % gold, 80 % diamond, 100 % platinum).

## 2026.11.03.18 — 16:00
### Achievements page
- The public **All achievements** list scrolls sideways like a player's page: each section is one line of cards (drag the
  scrollbar under it, Shift + wheel, or swipe) instead of a wrapping grid.

## 2026.11.03.17 — 15:48
### Re-read: deaths after the match is over (wait for it to finish)
- Deaths and respawns after a Capture Point match is decided (a team has 2 rounds) or the payload run is over (checkpoint 3
  or the timer at 0) no longer count: players are moved out of the arena then, which looked like deaths (about 8.6 % of
  all Capture Point deaths). `STATS_VERSION` 9: every replay (~29.5k) is read again after the restart; the "Processing N
  replays" counter in the top bar counts down. Death-based challenges settle when it reaches 0.

### Challenges
- **13 new "in one game" and related challenges** (ids 139-151, all counted in 4v4 games only): Untouchable, Marathon Bot,
  Comeback Kid, Statue, Lone Wolf, Ambidextrous, Speed Demon, Point Guard, Contested Ground, One-Trick Pony, Loadout
  Roulette, Mime Troupe, Victory Lap (emotes in a won game). Glass Cannon was left out.
- **Targets reviewed against the last 500 games of each player:** diamond and platinum are 30 % harder everywhere, and
  platinum targets that no one could reach in 500 games came down (totals, wins, pubs, hours, games). All gear (weapons,
  ordnances, tac mods, new gear included) shares one ladder per kind: use 5 / 15 / 50 / 150 / 350, "only X" in a day 3 / 6
  / 10 / 15 / 20 and in 7 days 5 / 10 / 15 / 30 / 50. Emote challenges are 4x harder. Arsenal Overload needs 5 weapons.

### Achievements page
- Opens with **Closest to your next medal**: one scrollable line, closest first. Every section is one scrollable line too,
  ordered the same way, with its own progress bar (`N/M completed · X %`); a player's page starts with the sections folded.
- The medal targets of a ladder are behind a **Medal targets** link (also written under each medal bar).

## 2026.11.03.16 — 12:53
### Fix: new replays not appearing
- The replay-folder scan stopped with "No such file or directory" when a folder (for example `htdocs/public/<id>`) was
  removed or unreadable while it was being listed, so no new replay was found until the next successful scan, which
  failed the same way. Such folders and files are now skipped (and logged) and the scan carries on.


## 2026.11.03.15 — 12:13
### Console
- New **Process missing replay files** (also `admin.bat process-missing`, menu 12): scans the replay folder, then queues
  every replay that has no match yet: new files, replays that finished without a match and ones that failed only
  because the file could not be read. Already queued, broken and hidden replays are left alone, and nothing is queued
  twice, so it is safe to run again. It replaces "Scan the replay folder" in the menu.
- Menu cleanup: the long Replays group is now Processing, Repair and Failed replays.

## 2026.11.03.14 — 03:42
### 3D views
- The 3D heatmap starts with the camera framing where the heat actually is (it used to frame the whole arena, leaving
  the paths small in the middle of an empty view).
- 3D playback in full screen: the play controls fold away ("Hide controls" / "Play controls") to give the whole view
  to the map.

## 2026.11.03.13 — 03:11
### Fixes from a full browser test
- 3D playback full screen: the latest-events list under the controls showed as one huge empty box (the skull and gear
  icons in it were stretched to the width of the screen); fixed at the cause, an old 2D-map style that reached every
  icon inside the 3D view.
- 2D playback: after switching from 3D to 2D the players, trails and names were not drawn until time moved (the map
  was sized before its picture had loaded); it now redraws when its size changes, also in full screen.
- Player page: the "Payload push / block" card's text no longer runs out of the card; the full screen button is the
  same size as the buttons next to it.

## 2026.11.03.12 — 02:51
### 3D playback: upside down is visible (head roll)
- The replay's head "up" direction is now kept (3D track file version 3: one more byte per player per sample). Players
  who roll or flip are drawn that way: the head turns around where it faces, with a white crest on top so the up side
  is clear, the body and the shoulders swing with it, and the First person camera rolls with the player.
- **What you must do:** nothing is required. A match processed before this has no roll: its 3D track is rebuilt from the
  replay the first time its 3D playback is opened (a few seconds), and every new import has it. To rebuild the whole
  archive in one go, run `backfill_tracks3d.bat --upgrade` (`--dry-run` first counts what it would do); it is slow but
  safe to stop and run again.
- Players who are not rolled look as before. Looking straight up or down has no "upright" to measure from and reads 0.

## 2026.11.03.11 — 02:43
### 3D playback: facing direction and arms
- Every player has an arrow on the floor under them in their team colour, pointing where they face (also readable from
  above), and a longer nose on the head.
- Arms are solid tubes from the shoulders to the hands instead of thin lines. Matches without recorded hand positions
  now show arms hanging relaxed at the sides. The "Hands" checkbox still turns hands and arms on and off.

## 2026.11.03.10 — 02:35
### Full screen for the 2D views, and more in the 3D full screens
- The 2D heatmap and the 2D playback have a full screen button: the whole view (legend, sliders, selectors, controls,
  scrubber, rosters) fills the screen and the map is sized to what is left.
- 3D playback in full screen: play, pause, skip, fight and speed controls, the scrubber, trail and name options, a player
  picker, copy link / clip, a way back to 2D, the latest events and the round banner.
### Heatmap colours
- Orange is more orange (team and per-player shades); the red and pink shades are gone.

## 2026.11.03.9 — 02:26
### 3D playback: buttons work again
- The camera buttons (Orbit, Top, Blue end ...), full screen, "?" and the Controls card did nothing: the 3D view sat on
  top of them and took every click. They are above it again.
### 3D heatmap: solid dots, full screen options
- Dots are drawn with normal blending instead of additive, solid out to 70% of their radius with a thin soft edge, so
  colours stay saturated instead of washing out over the map. The brightness slider sets how solid they are.
- Full screen now has an Options panel: the page's selectors (colour by, player, map ...), a switch per layer
  (All / None), heat and map opacity, and how to move around.

## 2026.11.03.8 — 02:11
### 3D heatmap: back to dots
- The ribbon drawing (neighbouring voxels joined by lines) looked too messy, so the 3D heatmap is drawn as dots again,
  exactly as in 2026.11.03.7.

## 2026.11.03.7 — 01:58
### 3D heatmap: continuous lines and depth
- Dots overlap (1.7 voxels wide, flat middle, soft edge) so paths are continuous lines instead of beads, with lower
  per-dot brightness so busy places do not clip to white.
- Depth cue: heat behind the point the camera looks at fades to 40%, so near and far paths can be told apart.

## 2026.11.03.6 — 01:51
### 3D heatmap: sharper lines
- Heat is drawn as thin solid dots instead of wide soft glows, brighter, with a higher floor so rarely used paths stay
  visible; the map starts more see-through (20%).

## 2026.11.03.5 — 01:48
### Remote worker: no pile-up, honest timings
- The PC stops claiming while 2 x uploads results wait to be sent (before, they piled up: 300+ waiting while the website
  saved ~30/min). Default uploads back to 6: the website saves one result at a time, more only adds waiting.
- "read" is now the real parse time (it used to include the wait in the pool's queue).
- The website reports, per result, how long it prepared, waited for the database lock and saved; the PC shows the averages.

## 2026.11.03.4 — 01:46
### Full screen for the 3D views
- A full screen button (⛶) in the toolbar of the 3D playback and the 3D heatmap. Esc leaves. Where the browser cannot take
  an element full screen (iPhone), the view fills the page instead.

## 2026.11.03.3 — 01:44
### Remote worker: more parallelism by default
- Readers default to all cores but one, 12 uploads at a time, and up to 3 x readers replays are claimed ahead.

## 2026.11.03.2 — 01:39
### Remote worker: much faster rebuilds
- `remote_worker.bat` now reads, claims and uploads at the same time: results go out from 6 upload threads (`--uploads N`)
  instead of one at a time, and up to 2 x workers replays are claimed ahead in batches, so the cores no longer wait.
- The progress line shows average seconds per replay for reading, sending and claiming, and how many are being read / sent.
- The website unpickles and checks the track files of a result in parallel; only the database write is one at a time.
  Update the NAS as well as the PC.

## 2026.11.03.1 — 01:07
### Heatmaps in 3D (new: match page, player page, Compare)
- **What:** next to the flat map there is now a **2D / 3D** switch. 3D shows the same layers (team, player, weapon, ordnance, tac mod, loadout, speed) as soft glows in 0.5 m cubes of space inside the see-through 3D map, so you can see *where above the floor* people spent their time. The legend, layer tick boxes and opacity slider work in both views. Orbit / Top / Reset buttons and a Map slider (how solid the map is drawn) sit on the view.
- **Not in 3D:** the deaths layer (death positions are stored without a height), and hover counts.
- **Coverage:** height comes from the 5 Hz 3D tracks. A match page builds them when missing (as 3D playback does). Player and Compare heatmaps use only matches that already have them and say "3D heat from X of Y matches"; matches fill in as they are imported or opened in 3D playback.
- **Fixed:** the Compare page's heatmaps asked for a cell size the server refuses, so they never showed (and said nothing). They now load at 0.1 m like the other pages.
- Internal: new `heatmaps3d.py` and `/heatmap3d` endpoints; the 2D rasteriser's path joining is now a shared helper (2D output unchanged).

## 2026.11.02.6 — 23:45
### Replays can be read on another PC (new, toggle in the Console)
- **Why:** reading replays is slow on the NAS (5-12x slower than on the PC) and takes CPU away from visitors.
- **How it works:** with **Console > Process replays on another PC** on (or `admin.bat remote --on`), the NAS stops reading replays itself. `remote_worker.bat` on the PC asks the website for queued replays, reads them from the replay share, and sends the finished results back; the website saves them exactly as if it had read the files. **Process replays on this server again** (`admin.bat remote --off`) turns it back; replays the PC was still holding are queued again at once, and so are ones the PC claimed but never answered for 30 minutes.
- **Safe by design:** the endpoints exist only when `ECHOVR_REMOTE_WORKER_SECRET` is set (same value on the NAS and the PC); the PC must run the same parser and stats versions (it is told to update otherwise); a result may only contain result data (never other code); damaged track files are left out; a PC that cannot see the share gives the replays back instead of marking them failed.
- **To do once:** set `ECHOVR_REMOTE_WORKER_SECRET` in the NAS's compose file (recreate the application) and in `settings.local.bat` on the PC; see docs/Setup.MD, "Remote processing". "Where replays are processed" in the Console and `admin.bat status` say which side is working and when the PC last asked for work.

### 3D playback
- **The payload (flamingo) moves:** it was part of the map file and stood at the start of the route while a box moved instead. It is now its own model (`<map>_payload.glb`, surge and fission), taken out of the map, with a ring in the attacking team's colour under it; it turns with the route.
- **Payload progress line:** the route is a thick dashed line and what the payload has covered is a thick solid line in the attacking team's colour, drawn over the map (a plain WebGL line is 1 px).
- **Easier to move around with mouse and keyboard:**
  - the wheel zooms towards the pointer, movement glides to a stop, right-drag (or Shift + drag) moves sideways, middle-drag zooms and the context menu no longer opens;
  - **W A S D** fly (Shift = 3x faster), **Q / E** down / up, **R** puts the camera back; speed follows the distance to what you look at.
- Weapon labels only update when somebody's weapon changes (a new list every tick made the labels redo their work).
- **Orange is orange:** the map files used `#ff3800` for the orange team's zones, which looks red next to the site's orange. Zones are now drawn in the site's team colours (orange `#ea7924`, blue to match).
- **Nicer maps:** warm key light and cool fill with colour-true tone mapping, distance fog, a gradient backdrop with a faint floor grid, readable dark walls instead of near-black, a cleaner glow on glowing parts, and a closer starting camera.
- **Right and middle mouse buttons:** no browser menu (in every camera, also over name labels and on a touch screen's long press), no middle-click autoscroll, no text selected while dragging, and they never pick a player.

### Server fixes found in a review of the 3D build
- 3D positions are built in their own small pool of processes: not behind a queue of replays, and a crash there is never blamed on the replays being read. A damaged replay answers "not available" (404), is not read again for 10 minutes, and at most 8 requests wait for builds at once.
- A damaged `tracks3d.bin` is built again; an older readable one is used when a rebuild is not possible; two writers no longer share one temp file.
- Map models are cached for a year only when asked for with `?v=<version>`.

### Heatmaps and player pages
- Heatmaps may take up to 90 s before the page says "Server busy" (they can take 10 s+ on the NAS right after a restart); the scroll wheel no longer zooms them (use + / -).
- Achievement badges: Starburst, Protostar, Quark, Blazar and Translocator challenges have their own icons; glyphs take the colour of the tier reached (grey = not started).
- Achievements of a player live at `/achievements/<name>/<id>` (old `?player=` links still work and move there); on a profile the Achievements section is above Loadouts and also shows when the chosen period has no games.

## 2026.11.02.5 — 23:21
### 3D playback: low CPU, plus the optional improvements
- **No full reprocess:**
  - Matches get their 3D positions the first time someone opens their 3D view, in about 1 s (a short "Loading 3D positions…"), instead of every replay being read again.
  - New imports get them as before.
  - The work runs in the low-priority replay processes, so the website stays fast.
- **Map models are cached for good**, per release: each visitor downloads a map once.
- **3D compare:** comparing two matches (`Compare with match #`) now has a **2D maps / 3D** switch and one camera picker for both.
- **Hands:** a **Hands** toggle shows each player's hands and arms, so you can see where they aim and throw.
- **Weapon icons** in the 3D name labels.
- **Not done:** better map models. There is no better source than the current hologram meshes, which are accurate to about 1 m.
- **To do:** restart, and rebuild the site (`run.bat` does it).

## 2026.11.02.4 — 21:26
### 3D playback (all 10 phases of docs/WebReplayer-Review.MD)
- **3D view on the Playback tab:**
  - A new **2D map / 3D** switch shows the match on a 3D map: players' head height, where each player looks (a cone), names, loadout swaps, trails (team or speed colour), skulls where players died, the payload route and cart, the capture point ring with progress, and round / checkpoint banners.
  - The clock, controls, roster, feed and fights are shared with the 2D view.
  - **Cameras:** Orbit, Top-down, Follow player and First person; **C** changes the camera, **1–9 / 0** pick a player, **Esc** lets go, and clicking a player picks them.
  - three.js is downloaded only when 3D is opened. Without WebGL the view says so and offers the 2D map.
- **Links:** the address keeps the view, camera, player and time (`?view=3d&cam=&player=&t=`). **Copy link** copies the current moment; **Copy clip** copies the last 10 s (`&until=`), and that link stops playback there. Both also work in 2D.
- **New endpoint:** `GET /api/matches/{id}/playback3d` (5 Hz head position and facing), from a new `tracks3d.bin` per match (16–118 KB). The parser now keeps `head.forward` (parser version 4).
- **3D map models:** `app/frontend/public/maps3d/*.glb` (2.47 MB), built and checked against replay positions by `app/tools/maps3d/` from the ec-web-replayer minimap meshes (MIT).
  - Combustion's placement is corrected.
  - **Hosting these meshes publicly is still to be decided:** see Open questions in `docs/WebReplayer-Review.MD`.
- **To do:**
  - Restart (2026.11.02.5 replaced the full reprocess this version planned: nothing is reprocessed).
  - Rebuild the site (`run.bat` does it; the Docker image installs the new `three` package).

## 2026.11.02.3 — 20:45
### Docs: 3D replay viewer review and plan
- New `docs/WebReplayer-Review.MD`: review of duncancarroll/ec-web-replayer (Three.js Echo Combat viewer; its ecranked.ddns.net data source is offline, 15 bugs listed) and a 10-phase plan to add a 3D view to the Playback tab using derived 3D tracks (no raw replay downloads). Linked from `docs/Phases.MD`.
- No code changes. **To do:** nothing.

## 2026.11.02.2 — 20:08
### Cloudflare tunnel: cloudflared pinned to 2026.10.7
- `docker-compose.yml` now runs `cloudflare/cloudflared:2026.10.7` (newest release) instead of `latest`, so the
  tunnel only changes version when the tag is edited.
- **To do:** in Container Station, recreate the application (or pull `cloudflare/cloudflared:2026.10.7` and recreate
  the `echovr-cloudflared` container). The tunnel token stays the same.

## 2026.11.02.1 — 18:34
### Leaderboard: re-rank by any column
- Click a column header (Games, Wins, Losses, Win rate, Hours played) to re-rank the **#** column by it, highest
  first; the podium shows that value too. Click the ranked stat's header (or pick another stat) to go back. The same
  players stay on the board (still filtered by the stat and minimum games); rank arrows compare the same ordering one
  period earlier. API: `GET /api/leaderboard?sort=<column>`.

### Discord-linked profiles: bio and profile picture (D54)
- Your Discord bot can link a Discord account to a player: `POST /api/bot/link {"discord_id", "user_id"}` with
  `Authorization: Bearer <ECHOVR_BOT_LINK_SECRET>` (also `/api/bot/unlink` and `/api/bot/lookup`, same body shape).
  The site trusts the bot. Linking again moves the link; one player per Discord account.
- On their own player page, a linked person logged in with Discord gets **Edit profile**: they can change **only**
  the profile bio (plain text, up to 500 characters) and whether their Discord avatar is shown as the profile
  picture. Name, stats and everything else stay read-only.
- **To do:** set `ECHOVR_BOT_LINK_SECRET` (docker-compose.yml) to a long random value and give the same value to the
  bot, then Recreate. Unset = bot linking off. The new `player_profiles` table is kept across rebuilds.

### Match ID on every match
- Match cards (home, matches page) show `#<id>` beside the mode, and match tables (player page etc.) have a
  **Match** column linking to it — the same number as the match page title.

## 2026.11.01.11 — 18:14
### Search boxes stop at 64 characters
- The previous update made the server refuse searches longer than 64 characters; the search boxes (top bar, home,
  compare, achievements, matches' player filter) now stop there too, so a long paste no longer shows an error.

## 2026.11.01.10 — 18:10
### Performance and security review
**Faster**
- **Heatmaps download about a third of the size:** cells are sent packed (binary, base64) instead of
  `[col, row, count]` JSON. A player's last 200 games: 1.1 MB → 0.47 MB; all games: 2.5–3.2 MB → 0.9–1.1 MB; one
  match: 207 → 95 KB. The browser also decodes them much faster. API change: layers carry `packed` instead of `cells`
  (Architecture.MD).
- **All-matches player heatmaps build ~4× faster the first time** (17–19 s → ~4.5 s): position files are now read 8
  at a time instead of one by one.
- **"Game in progress" never makes a visitor wait:** the last Twitch answer is sent at once and the next check runs in
  the background (before, whoever's request fell due waited ~0.5 s, and everyone arriving meanwhile with them).

**Safer**
- **Discord check (Console) only accepts a Discord id** (17–20 digits). Before, the text typed went straight into a
  Discord API address called with the bot token, so something like `../../channels/…` could read other things the
  bot can see. Same check for names looked up on the Permissions page, and stored ids no longer accept non-ASCII
  digits.
- **Filters only take real values:** map (the 4 maps), mode (payload / capture point), loadout gear (known codes),
  and length limits on name searches and ids. Every distinct value was its own cached answer and a full scan to
  build, so made-up values could keep the server busy and push useful answers out of the cache.
- **Icon upload** refuses an oversized file before reading it into memory.
- Checked and fine: login (OAuth state, signed HttpOnly / SameSite cookies, no open redirect), console and
  permission changes (Discord role checked on every command, custom header blocks other sites), no raw SQL from
  input, no HTML injection in the pages, security headers (CSP, frame, nosniff), bounded caches, rate limits,
  frontend packages (`npm audit`: 0 vulnerabilities).

## 2026.11.01.9 — 17:56
### Readability pass over every page
- **Numbers:** thousands separators everywhere (8,689 games, 1,194.6 h, 2,916 – 2,411, capture wins 4,176 – 4,305,
  "1,823 ranked players", search suggestions, compare, players list, achievements).
- **Player page:** new *Win rate* card; payload push / block totals read `31 h 24 m` instead of the clock-like
  `31:24:28`; "Last seen" capitalised.
- **Charts:** drawn at their real on-screen width, so axis labels are a readable 12 px in the small trend charts
  and the home page's players-per-hour chart (they shrank to ~4 px before).
- **Header:** stays on one line on a normal desktop width (the search box shrinks instead of wrapping).
- **Match page:** per-player tables no longer cut off on the right: the main loadout is stacked on three short lines,
  "+N more" points at Gear use. Pages are a little wider (1320 px) for the wide tables.
- **Home:** the most-popular-gear cards are wider so runner-up lines fit on one line.

## 2026.11.01.8 — 17:48
### Shorter version in the footer
- The footer said the date twice (`2026.11.01.7 (beta) · 1 Nov 2026, 17:01`). It now reads
  `Beta v26.11.1-8 · 1 Nov 2026, 17:48`: two-digit year, no leading zeros, the update of the day after the dash.
  Hovering it shows the full version. Same short form in `/api/health` (`version`; the full one is `build`) and the
  admin console. Docker tags, commits and changelog headings keep the full `2026.11.01.8`.

## 2026.11.01.7 — 17:01
### Home: "Game in progress" is always live
- It could show up or disappear up to ~3 minutes late (Twitch checked once a minute, Cloudflare kept the answer a
  minute, the page asked once a minute). It now has its own address, `/api/overview/live`, that no browser or
  Cloudflare keeps (`no-store`); the page asks every 10 s and the server checks Twitch every 10 s, one check shared by
  all visitors so the Twitch lookup service does not rate-limit the site. Now at most ~20 s behind the stream.
- `/api/overview/last-match` no longer includes `in_progress`.

## 2026.11.01.6 — 16:59
### Calendar version numbers, with release date and time
- Versions are now `YYYY.MM.DD.N` (release date + Nth update that day) with the release time, replacing Beta 1 – 80.
  Earlier changelog headings were renamed to match (old Beta number kept beside each).
- The website footer now shows only the version and its release date and time, e.g.
  `2026.11.01.6 (beta) · 1 Nov 2026, 16:59`; the ECRanked credit and search hint are gone from it.
- `/api/health` adds `released`. Docker images are tagged with the version (e.g. `2026.11.01.6`) and GitHub commits
  from `upload_to_github.bat` are labelled with it.
- New `python app/bump_version.py` makes the next version (date, counter, time) and adds its changelog heading.

## 2026.11.01.5 — Beta 80
### Leaderboard: wins, losses, win rate and hours on every board
- The table showed *Games* twice when ranking by games. Every board now shows Games, Wins, Losses, Win rate and
  Hours played beside the ranked stat; the column that is the ranked stat is not repeated.
- Podium cards show games, wins and win rate (again leaving out the ranked stat).
- These columns cover the same period and map as the board, all modes. Payload games have no winner, so they
  count as games but not as wins or losses.

## 2026.11.01.4 — Beta 79
### Playback: Fission payload track fixed
- One measured point of the Fission payload route (metre 160) sat at the end of the track, so once the payload
  passed 160 m the orange progress line shot ahead to the finish and back, and the cart briefly jumped there. The
  point is corrected; a test now checks every payload route for jumps.

## 2026.11.01.3 — Beta 78
### Heatmaps: super fine only
- Heatmaps on match and player pages are always drawn at **super fine (0.1 m)** detail. The *Detail* picker (fine,
  medium, coarse) is gone; the API's `cell` parameter now only accepts 0.1.

## 2026.11.01.2 — Beta 77
### Deaths: loading in no longer counts as a death
- **A player who loads into a server is parked at exactly (0, 0, 0)**, inside the play area, for ~10-17 s, then
  teleported out to the war room; that jump was counted as a death. Measured on 624 replays (every map, every year
  2021-2026): it is the load-in spot on Dyson, Combustion, Fission and Surge alike, at game start and for players
  joining mid-game, and no real death starts from exactly that spot. About 19,000 fake deaths in 7,000 of the 29,500
  matches.
- The parked time also no longer counts as time in the arena (it inflated *Stopped*, *Near mate* and *Near enemy*) and
  is left out of heatmaps, playback and match card thumbnails (a hot spot in the middle of every map).
- One load-in spot per map (`LOAD_IN_SPOTS` in `app/backend/stats/maps.py`); a new map gets no rule until measured.

### Match cards show where each team played
- Match cards on the home page and the Matches page show both teams' heat over the minimap. One request for the whole
  page (~5 KB per card, drawn on the server), so a page of cards costs no more than any other page.

### Home page
- **"Recently played"** replaces "Most played map": the map of the newest match, with its mode and score.

### Player pages
- **Profile addresses include the name**: `/players/ATM/1176721616202375269`. Old links (and links with an older name)
  still work and move to the current address.
- Fixed: running the site on Windows (`run.bat`), a profile address whose name contains a dot gave "Not found".

### Gear icons
- Weapons, ordnances and tac mods show their icon next to the name (match, player, home and replay pages); 17 so far.

### Console
- **Merge suggestions** in "Merge player records": player records that used the same name (ignoring case and
  punctuation, older names included), with games and first / last seen. "Use" fills in the form; the merge still needs
  Run. Records that played in the same match are flagged (usually two people with one name).
- **Merging keeps the earliest "First seen"**, also when the older record's first match is no longer stored.

### To do
1. Upload, wait for the GitHub Actions build, Recreate the container.
2. **Every replay is read again** (stats version 8) in the background, newest first. That takes hours on the NAS;
   pages show the current numbers until each replay is replaced. Progress: Console, "Status and import progress".

---

## 2026.11.01.1 — Beta 76
### Pages answer at once, even while the server is busy (caching, D53)
- **No more waiting for a recalculation.** Every new replay used to make the next visitor wait while the home page,
  leaderboard, profile or heatmap was recalculated (on the live site the home page numbers took 2.2 s). Now the last
  result is shown at once and recalculated in the background at most every 5 minutes (user choice,
  `ECHOVR_CACHE_REFRESH_S`), so pages are at most about 5 minutes behind new replays. Only a page nobody opened yet
  is calculated while you wait.
- **Match pages, playback, heatmaps, timeline, match lists and search are cached too** (they were recalculated on
  every visit), and every answer is kept compressed with an ETag: a repeat costs almost nothing, and a browser that
  already has the answer gets "304 Not Modified".
- **Measured on the full archive** with 16 visitors while a replay finished every second: requests answered in 30 s
  1,045 → 3,226; the slowest 10 % 1.8 s → 0.35 s; requests over 1 s 164 → 8; leaderboard median 2.2 s → 0.07 s.
- **Less work for every request**, images and scripts included: one layer instead of four for the security checks and
  headers (0.78 → 0.27 ms per request), and "has anything changed?" is read at most every 2 s instead of on every
  request (3 ms each time).
- **Replay processing gives way to visitors**: the import processes run at a lower priority, so pages stay quick while
  a big import runs; imports still use all the CPU the website leaves idle.
- **The achievements ranking no longer freezes the site** while it is calculated (Python's memory clean-up froze every
  request for up to 0.3 s at a time; paused during the calculation, which is also 18 % faster), and it is
  recalculated at most every 5 minutes.
- Teammates / opponents about 2x faster for players with many games, compare 4x.

### In the browser
- **Pages show the last data instantly** (also after a reload, kept per tab) and refresh in the background; numbers
  update by themselves when the refresh brings something new.
- **If the server is slow or out of reach**, pages keep what they show and the top bar says "Server busy · showing
  saved data" instead of an error; a request with no answer after 30 s is tried once more.
- **Fewer requests**: teammates, trends, the heatmap and achievements on player pages (and the compare heatmaps) load
  when you scroll to them; "Processing replays" is checked every minute and not at all in hidden tabs; the top-bar
  search starts at 2 letters (or a match number) and an older answer can no longer replace a newer one.

### Cloudflare cache (new)
- Public data answers may be kept by Cloudflare for 60 s (user choice, `ECHOVR_EDGE_CACHE_S`): repeats never reach the
  NAS. Login answers (and anything that depends on who is logged in) are never kept, errors are never kept.
- Needs one Cache Rule in the Cloudflare dashboard: docs/Setup.MD, "Cloudflare cache". **`check_cloudflare.bat` checks
  the setup** (also on the NAS: `docker exec -it echovr-replay-stats python app/cloudflare_check.py`).

### Upload script
- **`upload_to_github.bat` no longer stops at the list of changes.** A list longer than the window opened in Git's
  viewer, which waited for `q` (it looked as if nothing happened); the script now always prints it and goes on.

### To do
1. Upload, wait for the GitHub Actions build, Recreate the container. No replay is read again.
2. Add the Cloudflare Cache Rule and the rate limiting rule (Setup.MD, "Cloudflare cache"), then run
   `check_cloudflare.bat`: everything PASS.

---

## 2026.10.31.46 — Beta 75
### Match timeline, redesigned
- **Summary cards** above the chart: match length, rounds score, checkpoints, time in the lead, peak capture and estimated deaths per team.
- **Chart:** filled areas under the capture lines, alternating round bands labelled "Round 1, 2, …", and flags at each round win
  (coloured by the winner, showing the score) or payload checkpoint (CP1, CP2, …).
- **Death ticks** along the bottom of the chart, coloured by team (estimated, hover for the player).
- **Events list:** icons per event type, and hovering a row moves the chart crosshair to that moment.
- Website only: no restart or re-read needed, just rebuild/refresh the frontend.

---

## 2026.10.31.45 — Beta 74
- **Fix: the Playback tab turned the whole page blank** when the website had been updated but the server not restarted yet
  (the new page asked for playback data the old server does not send). The page now fills in what is missing, and any
  page that crashes shows "Something went wrong showing this page" with a Reload button instead of a blank screen.
  Browsers without `roundRect` drawing also work now. **After updating, restart the server** to get the new playback data.

---

## 2026.10.31.44 — Beta 73
### Match playback, round 2
- **Payload on the map:** the payload route is drawn (dashed, filled in the attackers' colour as it advances), with the
  cart, the checkpoints (filled once reached) and the finish flag. The route was measured from real Fission and Surge
  replays (median over 12 matches).
- **Capture point on the map** (Dyson, Combustion): a ring where players stand while capture progress rises, filled in the
  leading team's colour with the capture %. Its position is measured from replays and its size is an estimate.
- **Team fights:** 3+ deaths within 6 seconds are a fight: red bands under the slider, a "Fight" badge in the scoreboard
  while it happens, ⏮ / ⏭ Fight buttons (keys P / N) and a list of fights to jump to.
- **Death summary:** deaths per player with a bar, every death time as a clickable chip, first death, fights.
- **Loadout changes:** a "⇄ Nova · Detonator · …" label next to the player for 3 s, and lines in the event feed (the first
  loadout of each player is not counted as a change). Can be switched off.
- **Trail colour by speed:** trails can be coloured blue (slow) to red (12+ m/s) instead of by team.
- **Compare two matches:** type a match number under "Compare with match #" (or use `?vs=` in the link) to play two
  matches side by side on one shared clock.
- Event player ids now follow merged players, like the rest of the playback.

---

## 2026.10.31.43 — Beta 72
- **Deaths are obvious in the match playback:** a skull pops up on the map where each player died (estimated place),
  stays 5 seconds and fades, with the player's name under it in their team colour. Each team has a running skull
  count in the scoreboard, and the roster and event feed show a skull for fresh deaths.

---

## 2026.10.31.42 — Beta 71
- **Playback on the match page is much richer** (same recorded data, no re-import): a scoreboard bar (round score, clock,
  payload distance and checkpoints, or capture points), a roster per team with each player's current weapon, ordnance and
  tac mod, speed (m/s) and estimated deaths so far, click a player to highlight them, a red ring when someone dies,
  trails you can set to off / 5 s / 15 s / 1 min, ±10 s buttons, slower speeds (0.5x, 1x, 2x), event ticks under the slider
  (estimated deaths, round wins and checkpoints you can click to jump to), a live event feed, and keyboard shortcuts
  (space, arrow keys, [ ] for speed).
- A 3D replay viewer would need height and facing for every player, which the stored tracks do not have (they keep
  x / z only), so it needs the replays to be read again. Not part of this update.

---

## 2026.10.31.41 — Beta 70
- **Three per-game challenges are slightly harder** (user request): Full Team Salvo 40/50/60/75/90 % → 45/55/65/80/92 %,
  Super Ultra Hyper Turbo 13/17/21/25/30 m/s → 14/18/22/27/32 m/s, I'm Bat Bot 10/25/50/75/90 % → 15/30/55/80/92 %.
  Medals already earned are re-evaluated from the replays, so some players will drop a medal.

---

## 2026.10.31.40 — Beta 69
- **Weekly challenges are now a rolling 7 days** instead of a Monday-to-Sunday calendar week (user request). Your best
  7-day stretch counts, wherever it starts, so games on Friday and the following Tuesday are added together. Applies to
  every "in one week" challenge (Set Phasers to Kill!, Eat My Nova!, the other "only X" gear challenges, Gearhead, Pew Pew
  Proof, map / mode / pub counts, near mate / enemy, speed, inverted). Titles now say "in any 7 days"; the tab is "In any
  7 days". Games with other weapons never reset progress: a game only counts for "only X" when X is 95%+ of its time.
- Unlock dates for these challenges are now the date the 7-day stretch was completed. "Loyal Bot" (different weeks
  played) still counts calendar weeks.

---

## 2026.10.31.39 — Beta 68
- **Rate limit countdown:** when the site says "Too many requests", the message now counts down the seconds until you
  can try again (from the server's `Retry-After`), and the page reloads that data by itself when the wait is over
  (up to 3 automatic tries) instead of staying on the error.

---

## 2026.10.31.38 — Beta 67
- **Fewer "Too many requests" errors:** the per-visitor limit is raised from 30 to 60 requests a minute (bursts of 120)
  and from 600 to 1,500 an hour; heatmaps, playback, compare and downloads now cost 5 instead of 10. A player page
  loads many requests at once, so a few quick reloads used to hit the limit.
- **To do on the server:** `docker-compose.yml` sets these explicitly (`ECHOVR_RATE_LIMIT_PER_MIN` 60,
  `ECHOVR_RATE_LIMIT_PER_HOUR` 1500): Recreate the container so it picks them up.

---

## 2026.10.31.37 — Beta 66
- **Loadouts table is easier to read:** numbered rows, and "Time used" is now a bar on a track (scaled to the most used
  loadout) with the percentage beside it, instead of a tiny dot next to the number.

---

## 2026.10.31.36 — Beta 65
- **All tables are easier to read:** every table on the site now sits in its own panel (border, padding), headings are
  small muted capitals, rows highlight on hover, and side-by-side tables (teammates / opponents, status, gear use) have
  a wider gap so they no longer run together.
- **Checked in a browser** (desktop light/dark, phone width): trend charts now draw at their real size so axis labels are
  readable and sit in panels, gear use panels are equal height, long table headings wrap so the match stats table needs
  far less sideways scrolling, phone rows are cards inside the table panel, and the teammates "Time frame" label lines up.

---

## 2026.10.31.35 — Beta 64
- **Gear use is easier to read:** weapon, ordnance and tac mod tables on the player page are now separate panels with
  more space between them instead of running together.

---

## 2026.10.31.34 — Beta 63
- **Time frame filter for "Most played with / against":** player pages can now limit teammates and opponents to the last
  24 hours, 7 days, 1 month, 3 months, 6 months, 12 months or all time (rolling windows, not calendar periods).

---

## 2026.10.31.33 — Beta 62
- **Import progress bars can reach 100%:** "Match results and player stats", "Leaderboard" and "Achievements" now count
  against replays that could be read, not against all replays. Failed replays never produce a match, so they used to
  hold these bars just under 100% (e.g. 29,520 / 29,600). "Replays read and checked" still shows the failures.

---

## 2026.10.31.32 — Beta 61
### Security review (penetration test of a local copy configured like the public site)
- **Replay files cannot be downloaded:** no route reads the replay folder (it is also mounted read-only), and paths to
  `.echoreplay` files are now refused outright (404, also encoded or in capitals); a missing file such as `/x.txt` is a
  404 instead of the home page. Tested with path traversal, encoded dots and slashes, and guessed download routes.
- **The rate limit could be dodged** by sending a made-up `CF-Connecting-IP` header with every request (300 of 300 got
  through). The header is now believed only when the request comes from inside (cloudflared, the home network); a request
  that reaches the port from the internet is limited by its real address.
- **API documentation hidden:** `/docs`, `/redoc` and `/openapi.json` listed every route, the admin ones included. Off.
- **`/api/health` no longer shows the server folder path** (it answered anyone, without the bot checks).
- **New browser protections:** Content-Security-Policy (scripts and connections only from this site; fonts from Google,
  video from Twitch), Permissions-Policy, Cross-Origin-Opener-Policy, and HSTS when the visitor used https.
- Checked and fine: admin, console, permissions and icon endpoints refuse visitors who are not logged in with the role;
  changes (POST / PUT / DELETE) are refused site-wide; no cross-site access (CORS); odd input to players / leaderboard /
  limits is rejected; `//api`, `/API` and encoded-slash tricks never reach the data.
- If a page looks broken after the update (a missing font, the Twitch video), tell me: the CSP is the likely cause.

---

## 2026.10.31.31 — Beta 60
### Stricter limits against scrapers
- Data requests per visitor: **30 a minute** (bursts of 60), was 60 (bursts of 120). Heavy answers (heatmaps, playback,
  compare, downloads) count 10, was 5.
- **New hourly limit: 600 requests per visitor per hour**, so a slow scraper cannot copy the archive over a day either. A
  normal visit (a few requests per page) stays far below it.
- Settings: `ECHOVR_RATE_LIMIT_PER_MIN` (30) and `ECHOVR_RATE_LIMIT_PER_HOUR` (600) in `docker-compose.yml`; `0` turns a limit
  off. Restart the app container for it to apply.

---

## 2026.10.31.30 — Beta 59
### Leaderboard is faster
- **Switching the stat is instant** (about 1.3 s before, 0.03 s now on the full archive): one pass over the matches
  calculates every stat, and that result is now kept per period / map / public-private filter instead of per stat. The
  rank-change arrows reuse it too.
- **Requests for the same board wait for one calculation** instead of each starting their own (this also applies to the
  home page numbers, which use the same cache).
- Only the 50 players on the shown page are looked up and built, not all ranked players.
- The first view of a board after new replays are processed is still calculated once (about 1.3 s for the archive).
  Nothing has to be re-read.

---

## 2026.10.31.29 — Beta 58
### Achievements: every top medal reachable within a 4-month challenge window
Checked against a window of about 120 days / 17 weeks. Medals recalculate by themselves; nothing has to be re-read.
- **Regular** (days played): 5 / 15 / 30 / 60 / 100 (was up to 300 days).
- **Loyal Bot** (different weeks played): 3 / 6 / 9 / 12 / 15 (was up to 100 weeks).
- **Frequent Flyer** (games played): 10 / 50 / 200 / 750 / 2000 (was up to 5000).
- **Time Well Wasted** (hours played): 1 / 5 / 20 / 100 / 300 (was up to 500).
- **Overtime** (games of 10+ minutes): 5 / 20 / 50 / 150 / 500 (was up to 1000).
- **Unstoppable** (wins in a row): 4 / 6 / 8 / 10 / 12 (was up to 18).
- **Hot Day** (wins in one day): 3 / 5 / 8 / 12 / 16 (was up to 20).

---

## 2026.10.31.28 — Beta 57
### Achievements page loads fast
- **Cause:** the page asks for three things at once (the list, the recent unlocks, the top players) and every one of them
  started its own full calculation over all 8,090 players (about 20 s each, all at the same time), so the page sat on
  "Loading...". Now:
  - **One calculation at a time:** requests that arrive meanwhile wait for it instead of repeating it.
  - **The list and the recent unlocks answer at once** while the calculation runs in the background; the rarity numbers
    ("x % unlocked") appear on the next visit if it was not done yet.
  - **Results are kept on disk** (`data/database/achievements-cache.pkl`) and reused after a restart, so only players with
    new games are calculated again (the full calculation: about 23 s, once per new version; after a restart about 8 s).
  - A few lookups were made cheaper (the achievements calculation is about 15 % faster per rule).
- **Cyberkinetic Enhancements is easier and more realistic:** it needs **25+ games** instead of 50 (50 left out three
  quarters of the active players) and the ladder is 2.6 / 2.8 / 3.0 / 3.2 / 3.5 m/s (was 2.8 / 2.95 / 3.1 / 3.3 / 3.6).
  Of the players with 10+ games, about 30 % reach bronze, 20 % silver, 11 % gold, 4 % diamond and 0.7 % platinum.

---

## 2026.10.31.27 — Beta 56
### Achievements: gear released on 30 Oct 2026
- **Starburst, Protostar, Quark, Translocator and Overcharge now have the same ladders as the older gear** (the archive
  holds little of them yet, so these are estimates to retune once there is data): Veterans and Overclocked
  (games using it) 5 / 15 / 50 / 150 / 500; "only X in one day" 3 / 6 / 10 / 15 / 20; **6 new achievements**: "only X in one
  week" 5 / 10 / 15 / 30 / 50 for Starburst (Star Power), Protostar (Protostar Powerhouse), Quark (Quark Quake) and
  Translocator (Blink and You'll Miss It), and Overcharge in a day (Full Charge) and in a week (Charged Up).
- **Blazar and Dot Field were released too:** Blazar Veteran and Dot Field Veteran (5 / 15 / 50 / 150 / 500), "only X in one
  day" Blazing Trail and Dot to Dot (3 / 6 / 10 / 15 / 20), "only X in one week" Blazar Barrage and Dot Matrix
  (5 / 10 / 15 / 30 / 50): 6 more new achievements. Blazar of Glory and Connect the Dots are now 1 / 5 / 25 / 50 / 100 like
  the other "Beta Tester" achievements.
- Wording: these are called "experimental" instead of "unreleased".
- Medals recalculate by themselves; nothing has to be re-read.

---

## 2026.10.31.26 — Beta 55
### Achievements: similar ones now match, and unreachable medals fixed
- **Similar achievements share a ladder:**
  - Hold the Line = Special Delivery = Clean Sweep: 1 / 5 / 10 / 25 / 100 (Hold the Line was 1 / 5 / 15 / 50 / 200).
  - Point Taker and Cargo Hauler: 5 / 10 / 30 / 100 / 250 wins (bronze 5 like Centurion, top = half of Centurion's 500).
  - Weapons Master = Loadout Scholar: 1 / 5 / 15 / 50 / 100.
  - Experimental gear: Starburst Beta Tester, Protostar Prototype, Quantum of Quark and Now You See Me all 1 / 5 / 25 / 50 / 100;
    Blazar of Glory and Connect the Dots (rarest) 1 / 2 / 5 / 10 / 15.
  - The four "only <experimental gear>" day achievements use the released-gear ladder 3 / 6 / 10 / 15 / 20.
  - Starburst, Protostar, Quark and Translocator Veteran all 1 / 3 / 10 / 25 / 60.
- **Medals nobody could reach were lowered** (checked against the archive; the top medals now have at least ~0.1 %):
  Gearhead 4 / 8 / 15 / 30 / 50 games in a row (top was 0.0 %); Versatile Bot 1 / 2 / 4 / 8 / 15 days (gold was 0.4 %);
  Connect the Dots 1 / 2 / 3 / 5 / 8 games (no more than 24 in the archive); Overclocked 1 / 2 / 3 / 4 / 5 games (the most
  anyone has is 2). Medals recalculate by themselves; nothing has to be re-read.

---

## 2026.10.31.25 — Beta 54
### Achievements
- **Centurion is easier:** win 5 / 10 / 30 / 100 / 500 games (was 10 / 25 / 100 / 500 / 2000). 100 wins, the name's
  number, is now the diamond medal. In the archive 51 % of players (10+ games) reach bronze, 29 % silver, 11 % gold
  (was 5 %), 5 % diamond and 1 % platinum.
- **Grand Tour is easier:** wins on each of the four maps (the map with the fewest wins counts) 1 / 3 / 8 / 25 / 75
  (was 1 / 5 / 15 / 50 / 150): 38 % bronze, 17 % silver, 8 % gold (was 5 %), 4 % diamond, 1.6 % platinum.
  Medals recalculate by themselves; nothing has to be re-read.

---

## 2026.10.31.24 — Beta 53
### Achievements
- **The "All time" medals are easier to reach** (the original all-time section, ids 55-79):
  - Gear Veterans (games using it): 5 / 15 / 50 / 150 / 500 (was 10 / 30 / 100 / 300 / 1000)
  - 5th Loadout when? (different loadouts): 6 / 12 / 24 / 40 / 56 (was 8 / 16 / 32 / 48 / 64)
  - Pixel Party (deaths): 100 / 300 / 750 / 2,500 / 10,000
  - King of the Hill, Feed the Flamingo (games): 10 / 25 / 50 / 150 / 500
  - The four map achievements (games on a map): 5 / 10 / 25 / 75 / 250
  - King/Queen of Pubs: 25 / 75 / 150 / 350 / 1,000
  - Averages (50+ games): near a teammate 14 / 15.5 / 17 / 19.5 / 22.5 %, near an enemy 6 / 8 / 10 / 12.5 / 15 %, speed
    2.8 / 2.95 / 3.1 / 3.3 / 3.6 m/s, inverted 2 / 4 / 8 / 20 / 40 %
  Example: Pulsar Veteran gold goes from 7 % to 15 % of players.
- **Protostar, Quark and Translocator Veteran** (young gear) are 1 / 3 / 10 / 25 / 60 games (was 10 / 30 / 100 / 300 /
  1000): about 10-14 % of players reach bronze and 2-3 % gold (it was 2 % bronze, 0.1-0.2 % gold). Starburst Veteran
  is unchanged. Medals recalculate by themselves; nothing has to be re-read.

---

## 2026.10.31.23 — Beta 52
### Achievements
- **Medal order corrected:** bronze, silver, gold, **diamond, then platinum** (platinum is the top medal, it was the
  other way round). Every ladder keeps its targets; the fourth target is now diamond and the fifth platinum, on the
  badge, the progress bar and the text. "Completed" now means platinum. Medal Collector counts gold or better as before.
  Medals recalculate by themselves; nothing has to be re-read. (Earlier changelog entries still use the old order.)

---

## 2026.10.31.22 — Beta 51
### Achievements
- **Tech Support w/RAD_Natalie is easier:** time near a teammate over one week is now 22 / 27 / 32 / 40 / 55 % for
  bronze / silver / gold / platinum / diamond (was 25 / 30 / 35 / 45 / 60). In the archive about 56 % of players
  (10+ games) reach bronze, 37 % silver, 24 % gold (was 19 %), 13 % platinum and 3 % diamond. Nothing has to be re-read.

---

## 2026.10.31.21 — Beta 50
### Achievements
- **Super Ultra Hyper Turbo is a little easier:** top speed in one game is now 13 / 17 / 21 / 25 / 30 m/s for bronze /
  silver / gold / platinum / diamond (was 14 / 18 / 22 / 26 / 32). In the archive about 82 % of players (10+ games)
  reach bronze, 37 % silver, 10 % gold (was 7 %), 3 % platinum and 0.3 % diamond. Medals update by themselves; nothing
  has to be re-read.

---

## 2026.10.31.20 — Beta 49
### Achievements: sections with their own filters
- **Section order:** In one game, In one day, In one week, All time, then Experimental gear, Gear mastery, Wins,
  Payload, Capture Point, Activity, Emotes. Each section still folds away.
- **Each section has Completed / In progress / Not started filters** (with counts) for a player. Completed
  achievements are hidden until you pick Completed; the section opens on the first filter that has something. This
  replaces the single Completed / In progress tab at the top (Beta 47).
- **"Unreleased gear" is now "Experimental gear".** New **Capture Point** section (Clean Sweep, Point Taker); Payload now
  also holds Special Delivery, Hold the Line and Cargo Hauler (moved out of Wins). The "New challenges" heading is gone
  (the "new" tag stays on each badge); "Jump to new challenges" goes to Experimental gear.
- The catalogue (no player picked) shows every achievement without filters. Display only.

---

## 2026.10.31.19 — Beta 48
### Achievements
- **Every section can be folded away:** In one day / week / game / All time, the New challenges block and each of its
  themes. Click a heading (the count of achievements is shown), or use **Expand all / Collapse all**. Your choice is
  remembered in this browser. Display only.

---

## 2026.10.31.18 — Beta 47
### Achievements
- **Completed achievements move to a "Completed" tab** (diamond for ladders, 100 % for single-step ones). The page
  opens on **In progress**, so only what is still to do is shown; **All** shows everything. The tabs show their counts.
  Replaces the old Unlocked / Locked filter. Display only.

---

## 2026.10.31.17 — Beta 46
### Achievements: medal ladders for (almost) everything
- **Every achievement is now its own bronze / silver / gold / platinum / diamond ladder** (114 of 122; the yes / no
  ones such as Jack of All Trades, Forbidden Arsenal and Pew Pew Proof keep their single step). Each stays a separate
  achievement: daily, weekly and all-time versions of the same gear are still different entries.
- Period ladders count your **best day / best week / best game** (e.g. "Play games using only Pulsar in one day":
  3 / 6 / 10 / 15 / 20). The description lists every target, with units (%, m/s, min).
- The targets come from the real archive (docs/Achievement-Tiers-Proposal.MD): bronze is reachable for roughly a
  quarter to a half of active players, diamond for about 1 %. Hard old targets (35 m/s, 35 pubs a day, ...) are now the
  top steps; trivial ones ("near an enemy 2 %") got real steps. Clean Sweep / Special Delivery diamond is now 100.
- **Changed meaning:** Versatile Bot counts days on which you used all 12 equipables; My Other Chassis Is a Toaster
  counts games with 3 or fewer deaths; Hold the Line counts Payload defence wins; Centurion and the other counts are
  ladders. Anyone who completed an old rule is now gold (60 %) on it, with platinum and diamond above.
- **14 new challenges:** Frequent Flyer, Regular, Loyal Bot, Daily Grind, Time Well Wasted, Overtime (new "Activity"
  section), Hot Day, Point Taker, Cargo Hauler, Grand Tour, Weapons Master, Loadout Scholar, Wall of Steel, and
  **Medal Collector** (gold medals or better across all others: 5 / 10 / 25 / 50 / 75).
- No data is stored for achievements, so nothing has to be re-read.
- **Going back:** `version.bat beta-45` returns to the previous version, `version.bat latest` comes back (see below).

### Home page speed
- The two charts' data is now requested together with the overview instead of after it (was one request after the
  other); the Twitch player loads only once the page has settled and is on screen; map images load lazily.
- The server prepares the home page numbers at startup and caches the "players seen" chart; the heavy achievements
  ranking now starts only after them. The achievements calculation is back to the speed of Beta 45 (it was 50 % slower
  with the first ladders).

### Going back to an earlier version
- `version.bat` lists the versions, `version.bat beta-45` switches to Beta 45, `version.bat latest` returns to the
  newest. It refuses to switch while there are unsaved changes. Start the site with `run.bat` afterwards.

---

## 2026.10.31.16 — Beta 45
### Achievements
- **Name and status take the colour of the medal reached** (white, bronze, silver, gold, platinum, diamond), in both themes.
- **Progress to every medal is visible:** the bar is split into one segment per medal, each filled in that medal's
  colour with its target underneath (e.g. 1 / 5 / 10 / 25 / 50 games, or 25 / 50 / 75 / 100 %). Reached medals are
  highlighted. Display only; no re-read needed.
- Proposal for tiering all other achievements and adding new ones: docs/Achievement-Tiers-Proposal.MD (not applied yet).

---

## 2026.10.31.15 — Beta 44
### Gear use (match and player pages)
- **New "Gear use" section** for every weapon, ordnance and tac mod: **times picked** (switched to it, including
  the first one held; a blank gap such as a respawn is not a new pick), **games used** (player page) and **share
  of the time held**. The match page lists it per player; the player page has one table per gear type, following
  the period / map filters.
- Replays do not record shots, throws or tac mod uses (checked on a 31 Oct 2026 replay; noted in
  docs/ReplayData.MD), so those cannot be counted; the pages say so.
- Counted from data already stored (the loadout-change events): no re-read of the archive needed.

### Achievements
- **Tiered achievements:** Clean Sweep (win Capture Point games 2-0) and Special Delivery (deliver the payload to
  the end: win Payload games as the attacking team) now have five medals: **1 bronze, 5 silver, 10 gold,
  25 platinum, 50 diamond** games. The badge shows e.g. "14 / 25 for platinum"; progress is 20 % per medal and
  diamond counts as completed. New platinum and diamond medal frames. In the archive 62 % of players (10+ games)
  have a Clean Sweep bronze and 3 % would have diamond; 50 % / 2 % for Special Delivery.
- "Completed" on profiles now means 100 % (gold, or diamond for tiered ones); rarity counts tiered ones as
  unlocked from bronze.

### Matches
- **Removed the Export link** (CSV / JSON) from match pages.

### Player merges
- **Newest matches first:** replays a merge (or undo / repair) queues for re-reading are processed newest match
  first, so a merged player's latest games are right first.

- Nothing to do: restart the server.

## 2026.10.31.14 — Beta 43
### Home page
- **Announcement under the site description:** "Echo Combat has been released to Quest Standalone as of Oct 30th
  2026", with links to the [Discord](https://discord.gg/echo-vr-lounge) and [echovrce.com](https://echovrce.com).
- Nothing to do: refresh the page.

## 2026.10.31.13 — Beta 42
### Home page
- **Latest matches beside the live video are a compact, scrollable list:** one short row per match (small minimap,
  map, mode, score, winner, date and length), as tall as the video, scrolling to all 8 newest matches. Replaces the
  big cards, which did not fit next to the video. On narrow screens the list sits below the video and scrolls too.
- Nothing to do: refresh the page.

## 2026.10.31.12 — Beta 41
### Home page
- **Fixed:** the latest-match cards beside the live video were squashed to thin strips (every card shown, each
  cut to a sliver of minimap). Cards keep their full size again; only the ones that fit beside the video show.
- Nothing to do: refresh the page (restart the server if it was not restarted after Beta 40).

## 2026.10.31.11 — Beta 40
### Home page
- **Live stream in Latest matches:** the Echo Combat spectator bot
  ([twitch.tv/combat_stream_bot](https://www.twitch.tv/combat_stream_bot)) plays muted on the left, the newest
  matches are on the right (as many as fit beside the video, none cut off), with a "Live on Twitch" link. On narrow
  screens the video sits above one row of matches. Twitch only shows embeds on HTTPS pages (or localhost), so it
  works on the public site but not when opened by a plain-http LAN address.
- Nothing to do: restart the server to serve the new pages.

## 2026.10.31.10 — Beta 39
### Player merges
- **Merging players is now near-instant.** In every match where only one of the player's ids played (the usual
  case for an alt), the records are moved to the main player straight away instead of the replay being re-read from
  the share. Only matches where two of the player's ids played together are still re-processed. The result is the
  same as a full re-read (a test checks this). The console now shows "N replays updated now" and, if any,
  "M queued for re-processing".
- **Fixed:** two merged ids of the same player in one match (e.g. two alts, without the main) made that match fail to
  save, so it disappeared. They now stay separate in that match, like a main + alias already did.
- Undo is unchanged: it still re-reads the main player's replays, as the database alone can't tell which id a row
  came from.
- Nothing to do: no re-read needed after updating.

## 2026.10.31.9 — Beta 38
### Achievements
- **12 new achievements for the formerly unreleased gear (101-112), now 108 in total.** Found by scanning the 84
  new replays of 30-31 Oct: no gear codes the site did not already know, but Quark is now in 75 of 84 games,
  Translocator in 74, Starburst in 72, Protostar in 72, and Overcharge shows up for the first time (8 games).
  - Unreleased gear: Starburst Stream / Protostar Power Trip / Quark Storm / Here, There and Everywhere — use
    only Starburst / Protostar / Quark / Translocator for 10+ games in one day; Starburst / Protostar / Quark /
    Translocator Veteran — play 100 games using it; Beam Me Up — use Translocator and Dot Field in one game;
    Overclocked — play 5+ games using Overcharge.
  - Gear mastery: Arsenal Overload — use 6 different weapons in one game; Ordnance Overload — use 5 different
    ordnances in one game.
  - Targets checked against the new replays (D51). Attack Drone, Umbral Veil and Neutron are still not in any.
### Website
- **Player profiles show the Achievements section again before the start date**, tagged "Coming soon" with a
  "Sneak peek" link: the number of achievements and the start date (or "once the challenges start"), but none of
  the player's progress. Progress appears from the start date set in the console (previewers see it already).

### Upgrading to Beta 38
- QNAP: upload Beta 38, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.8 — Beta 37
### Website
- **Five achievements revealed early** in the sneak peek on the "Coming soon" page, in full (badge, name,
  description): Yeet and Delete (in one day), Sakura's Dancing Flamingo (in one week), My Other Chassis Is a
  Toaster (in one game), Feed the Flamingo (all time) and Clean Sweep (new challenge). The rest stay hidden as
  blurred "???" badges. The five are set in `REVEALED_IDS` in `app/backend/api/achievements.py`; icons chosen on
  the Console page apply to them.
- **"More being developed."** under New challenges, in the sneak peek and on the launched achievements page.
- **"Unreleased gear" is marked "Now public"**: on its card in the sneak peek and in its section hint on the
  launched achievements page.

### Upgrading to Beta 37
- QNAP: upload Beta 37, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.7 — Beta 36
### Website
- **Sneak peek on the "Coming soon" achievements page.** Below the Coming soon message, visitors see six mystery
  badges (blurred, grey, locked, named "???") and how many achievements each section holds: from the original
  ECRanked site In one day 20, In one week 25, In one game 5, All time 25; and 21 new challenges by theme
  (Unreleased gear 7, Gear mastery 3, Wins 6, Payload 3, Emotes 2). No names, descriptions or targets are shown
  or sent before the start date.
- `/api/challenges` now includes `peek` (those counts and the six badge pictures).

### Upgrading to Beta 36
- QNAP: upload Beta 36, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.6 — Beta 35
### Website
- **The "Achievements" menu item says "Coming soon · 96"** before the Flamingo Challenge start date: the number of
  achievements and challenges available (hover for "96 achievements available"). The "Coming soon" page on
  /achievements names the number too. Previewers still see the "preview" tag instead.
- `/api/challenges` now includes `total`, the number of achievements, for everyone.

### Upgrading to Beta 35
- QNAP: upload Beta 35, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.5 — Beta 34
### Website
- **Player profiles no longer show "Achievements — coming soon"** before the Flamingo Challenge start date set in
  the console. The achievements section appears on profiles from the start date on (Discord preview-role members
  still see it early, as on the achievements page).

### Upgrading to Beta 34
- QNAP: upload Beta 34, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.4 — Beta 33
### Website
- **"Matches recorded over time" has a "Per day" tab** next to per month / per year. It shows the 90 days up to the
  newest recorded match (the archive may stop before today), one bar per day split by map, with days without
  matches left empty rather than skipped. Labels read "28 Oct", tooltips "28 October 2026". The whole archive per
  day would be ~1,600 bars, too thin to read.

### Upgrading to Beta 33
- QNAP: upload Beta 33, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.3 — Beta 32
### Stats
- **A match recorded twice now counts once.** The archive has 426 matches saved in two (or more) files: same
  session, same time, usually one of them re-saved later at twice the size. Until now both copies counted, in every
  total: profiles, leaderboard, achievements, home page, trends, teammates, heatmaps and match lists (about 1.5 % of
  matches and ~2,500 player appearances counted twice).
- Only the most complete copy counts (longest, then most players, then most frames; identical copies: the file
  found first). The other copy keeps its match page, with a note linking to the counted one. Match lists show the
  match once.
- Back-to-back matches in the same lobby share a session id but do not overlap in time: they are separate matches
  and still all count.
- "Also recorded in" on a match page now lists only real copies of that match, not the other matches of the lobby.
- Nothing is re-read: the copies are found from the existing data at startup (~0.05 s) and whenever a replay is
  saved. A new index is added to the database at startup (~0.1 s).

### Website
- **"Matches recorded over time" shows the latest month again.** The chart labelled every other bar counted from the
  first one, so the newest bar was often unlabelled; labels now count back from the newest. Same fix for the other
  bar and line charts (players per day / hour, player trends).
- Month labels read "Oct 2026" instead of "2026-10" (tooltip: "October 2026"); player trend weeks read "Wk 43 2026".

### Upgrading to Beta 32
- QNAP: upload Beta 32, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import. Totals drop
  slightly (the counted-twice matches), as intended.

---

## 2026.10.31.2 — Beta 31
### Website
- **Merged players no longer show up twice in the search box** at the top of the site. The Players page already
  hid them; the quick search still listed the merged ID with 0 games.
- **Old links to a merged ID open the main player's profile** (the address changes to the main player) instead of an
  empty profile with 0 games. Undoing the merge gives the ID its own profile back.

### Upgrading to Beta 31
- QNAP: upload Beta 31, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## 2026.10.31.1 — Beta 30
### Import
- **New replays reach the site within ~2-3 minutes** instead of up to ~7. Between the full scans (every 5 min) the
  server now checks the replay folders every 15 s (~16 ms on the share, vs ~4 s for a full scan); when a file is
  added, removed or renamed, the folder's modified time changes and a full scan runs straight away.
- A replay that is still settling (written in the last 2 minutes) is scanned again as soon as it is old enough,
  instead of waiting for the next full scan.
- Replays copied into the folder are no longer read half-copied: Explorer / robocopy keep the original modified time,
  so the copy time now counts towards the 2-minute wait too.
- Full scans read only the columns they compare from the database, so the more frequent scans stay cheap.
- New setting `ECHOVR_QUICK_CHECK_S` (default 15; 0 = off). No re-import.

### Upgrading to Beta 30
- QNAP: upload Beta 30, wait for the Actions run, Recreate. Windows: restart `run.bat`.

---

## 2026.10.30.29 — Beta 29
### Import
- **Reading a replay takes ~12 % less processor time** (parser and stats; same results, checked on 13 replays:
  stats, events and position files byte for byte). Helps where the processor is the limit (the NAS, 4 processes);
  no re-import.
- Measured on the PC: the import is limited by reading from the share (45-58 MB/s at its fastest, whether 2.6 or
  4.2 files/s), not by processing (8 processes could read ~700 MB/s), so it is not faster there.

### Upgrading to Beta 29
- QNAP: upload Beta 29, wait for the Actions run, Recreate. Windows: restart `run.bat`.

---

## 2026.10.30.28 — Beta 28
### Website
- **Player heatmaps 7–11x faster** (D50), same picture as before (checked cell by cell on 600 real matches, every
  mode and cell size). 1000 matches: team 5.1 → 0.6 s, speed 8.1 → 0.8 s, loadout 5.4 → 0.7 s, 0.1 m cells
  13.9 → 1.6 s.
- **Home page 3x faster** to build (470 → 160 ms): two new database indexes for "Most popular gear" and "Fastest
  player".

### Upgrading to Beta 28
- QNAP: upload Beta 28, wait for the Actions run, Recreate. The first start adds the two indexes (about a second;
  the database grows ~15 MB). No re-import.
- Windows: restart `run.bat` (it installs the new `numpy` package by itself).

---

## 2026.10.30.27 — Beta 27
### Website
- **Home, "Matches recorded over time"**: one stacked bar per month (or year) split into the four maps (Combustion,
  Dyson, Fission, Surge), with a key above the chart; hovering a bar lists the matches on each map.
- **Home, "Most active this week"**: a ranked list instead of a table: gold / silver / bronze badges for the top
  three, a bar comparing each player's matches with the leader's, and win rate with the number of wins.

### Upgrading to Beta 27
- QNAP: upload Beta 27, wait for the Actions run, Recreate. Windows: restart `run.bat`.

---

## 2026.10.30.26 — Beta 26
### Website
- **Faster pages: important data is kept in RAM** (D49). First loads measured on the full archive (29k matches):
  leaderboard 680 → 235 ms (2.9x), player profile 150 → 60 ms (2.6x), home page 560 → 480 ms. Reading a match's
  position file is 18x faster once it is in RAM (heatmaps, playback, timeline); big player heatmaps gain ~10 %,
  as drawing the grid is most of their time.
  - The database is memory-mapped and read into RAM when the app starts (`ECHOVR_DB_CACHE_MB`, default 1024).
  - Decoded position files are kept in RAM, least recently used out first (`ECHOVR_TRACK_CACHE_MB`, default 512,
    ~7,500 matches). `0` turns either off.

### Upgrading to Beta 26
- QNAP: upload Beta 26, wait for the Actions run, Recreate. Optional: add the two `ECHOVR_*_CACHE_MB` lines from the
  new `docker-compose.yml`; lower them if the NAS has little RAM (the defaults use up to ~1.5 GB).
- Windows: restart `run.bat`.

---

## 2026.10.30.25 — Beta 25
### Website
- **Protection against scrapers** (D48). Visitors notice nothing; the website's data now only goes to the website
  itself:
  - Scripts that call the data API directly (Python, curl, scraping tools, headless browsers) get "Automated access
    to this site's data is not allowed".
  - AI crawlers (GPTBot, ClaudeBot, CCBot, Bytespider, …) are refused on every page; a new `robots.txt` asks them to
    stay away and keeps search engines out of the data API (the pages can still be found on Google).
  - Each visitor can make 60 data requests a minute, bursts up to 120 (heatmaps, playback, compare and downloads
    count 5). Beyond that the site answers "Too many requests" for a few seconds. Change it with
    `ECHOVR_RATE_LIMIT_PER_MIN` in `docker-compose.yml` (0 = off).

### Upgrading to Beta 25
- QNAP: upload Beta 25, wait for the Actions run, Recreate. Optional: add the `ECHOVR_RATE_LIMIT_PER_MIN` line from
  the new `docker-compose.yml` to yours (60 is the default without it).
- Cloudflare (recommended): Security > Bots > turn on *Block AI bots* as well as *Bot Fight Mode* (Setup.MD,
  Public website step 6).
- Windows: restart `run.bat`.

---

## 2026.10.30.24 — Beta 24
### Website
- **Player profiles**: the **This is me / Not me** button and the **Export CSV · JSON** links are gone (user,
  2026-10-30). With "This is me" goes what it did: your own rank is no longer pinned above the leaderboard or
  highlighted in it, and Compare no longer adds "you" automatically. The player download
  (`/api/players/{user_id}/export`) and the leaderboard's `player` option are removed too. Match downloads stay.

### Upgrading to Beta 24
- QNAP: upload Beta 24, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.23 — Beta 23
Speed-ups only: every number, heatmap and achievement is the same as in Beta 22 (checked by comparing the old and
new results on the full database and on real replays).

### Importing
- **Reading replays is about twice as fast** (58 MB replay: 1.04 s → 0.54 s of processing): frames are parsed with
  `orjson`, timestamps without `strptime`, and files are read from the share in 1 MB chunks instead of line by line
  (fewer network round trips). No re-read: parser and stats versions are unchanged.

### Website
- **Player heatmaps**: first view 1.9 s → 0.85 s (last 200 matches), 22.5 s → 11 s (last 5000); opening one again
  328 ms → 25 ms. Match heatmaps 78 ms → 39 ms.
- **Achievements ranking** (rarity, recently completed, achievement leaderboard): after a new replay only the
  players in it are recalculated (3 s instead of 15 s). This ran in the web server, so the whole site was slower
  during those 15 s after every new replay.
- **Smaller first download**: each page's code loads when it is first opened (initial script 372 KB → 297 KB), and
  the browser keeps the site's script / style files instead of asking for them again.
- Compression is quicker (level 4 instead of 9: 12x faster for 8 % more bytes on the largest answers).

### Upgrading to Beta 23
- QNAP: upload Beta 23, wait for the Actions run, Recreate (installs the new `orjson` package).
- Windows: restart `run.bat` (installs `orjson` automatically).

---

## 2026.10.30.22 — Beta 22
### Website
- **Home page rearranged, most useful first**: search, then what is happening now (matches today, this week, how
  long ago the last match was, most played map), the **latest matches**, **most active this week** next to
  **players seen in Combat**, then matches per map, popular gear, and finally the **all-time** numbers (totals and
  global stats together) with the matches-over-time chart at the bottom. Nothing was removed.

### Upgrading to Beta 22
- QNAP: upload Beta 22, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.21 — Beta 21
### Website
- **The Admin tab is gone.** Everything it did is on the Console page: **Export achievements and challenges**
  lists every achievement with its rule and icon, changes icons and downloads a CSV (the Excel download is
  replaced by the CSV). Icons can now only be changed by Console users.
- The **Admin** permission (Permissions page, admin.bat options 15 / 17) now gives the **Status page** and the
  Preview. "Check a member's access" shows *Admin*, *Preview* and *Console page*.
- Fixes Beta 20, which was uploaded halfway through this change: its Admin tab showed an error.

### Upgrading to Beta 21
- QNAP: upload Beta 21, wait for the Actions run, Recreate.
- Windows: run `run.bat` (it no longer needs openpyxl).

---

## 2026.10.30.20 — Beta 20
### Website
- **Status page** (menu: *Status*, for admins and Console users): live progress of replay processing, updated
  every 10 seconds. Tiles for finished %, waiting, speed, time left and failed; a progress bar per stage (replays
  read, match stats, players, timeline events, position tracks, **heatmaps**, leaderboard, achievements) and whether
  the achievement leaderboard is being recalculated; the files being processed right now; the replay folder (reachable,
  last scan, new / changed files); replays finished per minute over the last hour; progress per year; matches per map.
- **Icon editor**: "Upload PNG" is now a large upload box at the top ("Upload your own icon"): click it to choose a
  PNG or drop the file on it. Below it: "Or pick a built-in badge" and **Reset to original**. (Before, the upload
  link looked like plain text.)

### Upgrading to Beta 20
- QNAP: upload Beta 20, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.19 — Beta 19
### Website
- **Permissions page** (menu: *Permissions*, for Console users): give or take away the **Admin tab**, the
  **Console** and the **Preview**, each by **Discord role** (everyone with it; picked from the server's roles by
  name) or by a **person's Discord user id**. Changes apply straight away and are kept across updates. Admins and
  Console users also get the Preview. Each change is written to the server log with who made it.
- The ids in `ECHOVR_DISCORD_PREVIEW_ROLES` (the YAML) are shown on the Console card as **YAML, fixed**: they
  always have the Console and cannot be removed on the page, so the owner cannot be locked out.
- **Console page > Export achievements and challenges** now shows each **icon**. Click one to pick another badge,
  upload a PNG or **reset it to the original**. Console users can change icons as well as admins.
- The Console page's view-only role lists (options 14, 15, 17) are gone: the Permissions page replaces them.
  "Check a member's access" stays.

### Admin console
- Option 16 (`discord-check`) follows the Permissions page too (user ids and roles for all three permissions).
- Options 14 / 15 / 17 still edit preview roles, admin roles and admin users (the same lists as the page); console
  roles / users and preview users are set on the Permissions page.

### Upgrading to Beta 19
- QNAP: upload Beta 19, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.18 — Beta 18
### Website
- **Console page > Achievements > Export achievements and challenges**: every achievement and challenge with just
  its **Name** and **How to win it** (the rule text shown on the website; "(deaths are estimated)" where that
  applies). Filter the list, **Copy** it (pastes as two columns into Excel / Google Sheets) or **Download CSV**
  (`EchoVR-Achievements.csv`, always the full list). Console access only, checked with Discord on every request.

### Upgrading to Beta 18
- QNAP: upload Beta 18, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.17 — Beta 17
### Website
- **Console page tidied up**: plain names instead of menu numbers, clearer help text, results as cards (Done /
  Failed, time, Clear), and messages that name the page's buttons instead of console commands.
- **Console access is checked on every command**, straight from Discord: a role taken away stops working at once
  (the menu tab can take up to 5 minutes to go), and when Discord cannot be asked the command is refused. A forged
  or missing login gets nothing, and refused attempts are written to the server log.
- A person's user id in `ECHOVR_DISCORD_PREVIEW_ROLES` now gives the preview too (before: only the Console page),
  even if they are not in the Discord server.

### Admin console
- Option 16 (`discord-check`, also "Check a member's access" on the Console page) now shows only the three
  permissions: **Admin tab**, **Preview** and **Console page** (yes / no), not the person's Discord roles.

### Upgrading to Beta 17
- QNAP: upload Beta 17, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.16 — Beta 16
### Website
- Console page: `ECHOVR_DISCORD_PREVIEW_ROLES` may also hold a **person's Discord user id** (right-click them >
  Copy User ID), not only role ids: that person gets the Console tab whatever their roles.
- Console page, options 14 / 15: only the roles that are set are listed. The list of every role in the Discord
  server (for picking one in admin.bat) is no longer shown there; it looked like everyone was an admin.

### Admin console
- Option 16 (`discord-check`) also says whether the person gets the Console page, and warns when
  `ECHOVR_DISCORD_PREVIEW_ROLES` is not set.
- Options 14 / 15: the list of every server role is now headed "All roles in the Discord server, to pick from".

### Upgrading to Beta 16
- QNAP: upload Beta 16, wait for the Actions run, Recreate (this also brings Beta 15's Console page live).
- Windows: restart `run.bat`.

---

## 2026.10.30.15 — Beta 15
### Website
- **Console page** (menu: *Console*): `admin.bat` on the website, for Discord members with a role listed in
  `ECHOVR_DISCORD_PREVIEW_ROLES` (docker-compose.yml / environment). Roles picked as preview roles in the admin
  console (option 14) do **not** get it. Every admin.bat option, same numbers: find / merge / undo merges, launch and
  challenge dates, status, repair, hide / show replays, re-process, scan, rescan everything, check a Discord member.
  The page asks before anything big and shows what the console printed. Changes apply straight away.
- Who gets the preview / Admin tab (options 14, 15, 17) is only **shown** on the Console page; changing it stays in
  `admin.bat`, so a console role cannot hand out access.
- Each command run from the page is written to the server log with the person's Discord name and id.

### Upgrading to Beta 15
- QNAP: upload Beta 15, wait for the Actions run, Recreate. Put the console role id(s) in
  `ECHOVR_DISCORD_PREVIEW_ROLES` in docker-compose.yml (several separated by commas) before Recreate.
- Windows: set `ECHOVR_DISCORD_PREVIEW_ROLES` in settings.local.bat, restart `run.bat`.
- Members see the Console tab after logging in again (or within 5 minutes).

---

## 2026.10.30.14 — Beta 14
### Admin console
- **Option 17, Discord admin users** (`admin.bat admin-users --add <user id>`): make a **person** an admin by
  their Discord user id (right-click them > Copy User ID). They get the Admin tab and the preview whatever their
  roles. `--remove <user id>` takes it away.
- Options 14 / 15 now refuse an id that is not a role in the server (for example a person's id) and say where it
  belongs; option 17 refuses a role id.
- `discord-check` shows admin users too.

### Upgrading to Beta 14
- QNAP: upload Beta 14, wait for the Actions run, Recreate. Then in the container terminal:
  `python app/admin_console.py admin-users --add <user id>` for each admin, and / or
  `python app/admin_console.py admin-roles --add <role id>` for an admin role.
- Windows: restart `run.bat`.

---

## 2026.10.30.13 — Beta 13
### Admin console
- **Option 16, check a Discord member's access** (`admin.bat discord-check <discord user id>`): asks Discord what
  the website sees for one person: whether they are in the server, their roles (by name, marked admin / preview),
  and whether they get the Admin tab and the preview. Says what is wrong when the bot token is refused, the bot is
  not in the server, or no admin role has been set.

### Website
- Logging in again re-checks your Discord roles straight away (before: up to 5 minutes).
- A failed role check (bad bot token, bot not in the server) is now written to the server log.

### Upgrading to Beta 13
- QNAP: upload Beta 13, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## 2026.10.30.12 — Beta 12
### Admin console
- **Option 14, Discord preview roles**: lists the roles in your Discord server (by name, via the bot) and marks the
  preview ones. Type a number to give that role the preview, `-` + number to take it away. Changes apply on the
  website straight away and are kept across database rebuilds. Command line: `admin.bat preview-roles --server`,
  `--add <role id>`, `--remove <role id>`.
- **Option 15, Discord admin roles**: same as option 14, for the roles that get the website's Admin tab.
- `admin.bat` reads `settings.local.bat` too, so the bot token is available to it on Windows.

### Website
- **Admin tab** (only for logged-in Discord members with an admin role): every achievement and challenge with the
  requirement players see, how to achieve it, how progress is measured and notes on the terms; filterable.
  **Download Excel** gives the same list (plus a "How it works" sheet and a summary). Both are built from the live
  rules each time, so the link always matches the website.
- **Change achievement icons** in the Admin tab: click an icon, then pick another badge image, upload your own PNG
  (at most 512 KB and 1024 x 1024), or reset to the default. The new icon shows everywhere on the site at once and
  is kept across updates. This is the only change that can be made on the website; everything else stays in the
  admin console.
- **Log in with Discord** button in the top-right corner of the menu bar on every page (when the Discord login is set
  up). Logging in brings you back to the page you were on; logged in, the corner shows your name and *Log out*.
- Admins also see achievements before the launch, like previewers.
- Discord login only needs the client secret and bot token; who gets the preview comes from the admin console.
  `ECHOVR_DISCORD_PREVIEW_ROLES` still works but is optional.

### Upgrading to Beta 12
- QNAP: upload Beta 12, wait for the Actions run, Recreate. Then open the admin console in the container and use
  option 14 to pick the preview role and option 15 for the admin role.
- Windows: restart `run.bat`.

---

## 2026.10.30.11 — Beta 11
### Website
- **Preview with Discord**: before the launch date, members of the EchoVR Combat Discord server with the preview
  role can see achievements and challenges. On the "Coming soon" page: *Have preview access? Log in with Discord*.
  Logged in, the top bar shows your name and *Log out*; the menu shows "preview" next to Achievements and the page
  says it is a preview.
- Previewers see progress over **every match in the archive** until the launch; from the launch date everyone sees
  only matches from that day on.
- Without the role, or not logged in, it stays "Coming soon". Giving or removing the role works within 5 minutes.

### Upgrading to Beta 11
- Set up the Discord login once (Setup.MD, *Discord login*): add the two redirect addresses in the Developer Portal,
  then fill in the client secret, bot token and preview role id. Until then the site works as in Beta 10.
- Windows: put the three values in `settings.local.bat`, then restart `run.bat`.
- QNAP: upload Beta 11, wait for the Actions run, edit the application (replace the three `YOUR_...` values,
  `ECHOVR_PUBLIC_URL` is already `https://echocombat.com`), then Recreate.

---

## 2026.10.30.10 — Beta 10
### Website
- **Achievements and challenges are "Coming soon"** until their start date. The Achievements page shows a
  "Coming soon" message (with the start date once one is set), the menu entry gets a "soon" tag, player pages show
  "Achievements — coming soon" instead of progress, and "Achievements" is left out of the leaderboard's stat list.
  Nothing about achievements can be read from the site before then (the API answers `coming_soon`).
- From the start date on they go live by themselves and **only count matches played from that date**.

### Admin console
- Option 5 is now **Achievements launch / Flamingo Challenge period**. The start date is the launch date; the
  console says whether the website currently shows "Coming soon" or is live. Command line:
  `admin.bat challenge --start YYYY-MM-DD` (end date optional).

### Upgrading to Beta 10
- Windows: restart `run.bat`. Achievements are hidden until you set a start date with `admin.bat` (option 5).
- QNAP: upload Beta 10, wait for the Actions run, then Recreate the application in Container Station.

---

## 2026.10.30.9 — Beta 9
### Website
- **Processing indicator**: while replays are still being read in the background, a small spinning wheel with
  "Processing N replays" shows in the top bar next to the site name, on every page. It checks every 15 seconds and
  disappears once everything is read. On phones only the wheel shows; tap/hover it for the count.
- New public endpoint `/api/overview/processing` (`{"pending": N}`) behind it.

### Upgrading to Beta 9
- Windows: restart `run.bat`.
- QNAP: upload Beta 9, wait for the Actions run, then Recreate the application in Container Station.

---

## 2026.10.30.8 — Beta 8
### Website
- **Long player names stay on one line**: in stat cards (home page Global stats, match page highlights) and on the
  leaderboard podium the name's text gets smaller until it fits the box. Extremely long names stop shrinking at a
  readable size and end in "…"; hover for the full name.
- **Match page highlights** (Fastest, Most mobile, …) stretch across the row, so long names fit at a normal size.

### Upgrading to Beta 8
- Windows: restart `run.bat`.
- QNAP: upload Beta 8, wait for the Actions run, then Recreate the application in Container Station.

---

## 2026.10.30.7 — Beta 7
### Website
- **Global stats** is back on the home page (https://echocombat.com), between "Most popular gear" and "Matches per
  map". The separate Global stats page and its menu entry are removed.
- **Home** menu entry, first in the menu: back to the home page from anywhere.

### Upgrading to Beta 7
- Windows: restart `run.bat`.
- QNAP: upload Beta 7, wait for the Actions run, then Recreate the application in Container Station.

---

## 2026.10.30.6 — Beta 6
### Website
- **Global stats** has its own page in the menu (`/stats`); it is no longer on the home page.
- **Import page removed** from the public website (admin information): no menu entry, no page, and the import /
  replay lists (`/api/import`, `/api/replays`) are switched off.

- **Long player names** no longer spill out of stat cards, the leaderboard podium or match name chips: they
  wrap onto the next line inside the box.

### Admin console
- **Status** (menu 6, `admin.bat status`) now shows the import progress: % finished, matches, replays being redone
  after an update, speed over the last 10 minutes, time left, last replay finished.

### Upgrading to Beta 6
- Windows: restart `run.bat`.
- QNAP: upload Beta 6, wait for the Actions run, then Recreate the application in Container Station.

---

## 2026.10.30.5 — Beta 5
### Server
- The QNAP NAS no longer builds the app (its Docker has no `git`, so building from GitHub failed). GitHub Actions now
  builds the image on every upload and publishes it to `ghcr.io/vibinator/echocombat-replay-stats` (Intel/AMD and
  ARM); `docker-compose.yml` downloads it. The YAML no longer contains a GitHub token: Container Station logs in to
  ghcr.io with a read-only token instead.
- Replay folder on the NAS: `/share/ECRanked/ECRanked`.

### Upgrading to Beta 5
- Windows: nothing to do; restart `run.bat` to see "Beta 5" in the footer.
- QNAP: upload Beta 5, wait for the Actions run, add the ghcr.io registry login in Container Station, then create
  the application with the new `docker-compose.yml` (Setup.MD, QNAP NAS).

---

## 2026.10.30.4 — Beta 4
### Website
- Ready to be public at **https://echocombat.com**: `docker-compose.yml` now also runs a Cloudflare Tunnel
  (`cloudflared`), so the NAS needs no open router ports and the home IP stays hidden. Steps in Setup.MD
  (Public website: echocombat.com).
- Every page is sent with basic browser security headers (no content sniffing, no framing by other sites,
  limited referrer).
- `upload_to_github.bat` also stops if a Cloudflare tunnel token is in a file to upload.

### Upgrading to Beta 4
- Windows: nothing to do; restart `run.bat` to see "Beta 4" in the footer.
- QNAP / echocombat.com: upload Beta 4 to GitHub, set up Cloudflare (Setup.MD), add the tunnel token to the YAML,
  recreate the application.

---

## 2026.10.30.3 — Beta 3
### Server
- Can run on a QNAP NAS (or any Docker host): new `Dockerfile`, `docker-compose.yml` and `.dockerignore`. Pasting
  `docker-compose.yml` into Container Station downloads the app from GitHub, builds it and starts it; replays are
  mounted read-only, the database lives in a NAS `data` folder that survives updates.
- `upload_to_github.bat` also stops if any file to upload contains a GitHub token.

### Upgrading to Beta 3
- Windows: nothing to do; restart `run.bat` to see "Beta 3" in the footer.
- QNAP: upload Beta 3 to GitHub, then follow Setup.MD (QNAP NAS): token, folder paths, paste into Container Station.

---

## 2026.10.30.2 — Beta 2
### GitHub
- The replay share's network address is no longer in the repository: Setup.MD and Architecture.MD show a placeholder
  (`\\<server>\<share>\Replays`). Your own setup is unchanged (`Z:\ECRanked\Replays`, or `ECHOVR_REPLAY_SOURCE`).
- `upload_to_github.bat` also stops if any file to upload contains a local network address (192.168.x.x).

### Upgrading to Beta 2
- Nothing to do; restart `run.bat` to see "Beta 2" in the footer.

---

## 2026.10.30.1 — Beta 1
Baseline: everything up to and including Phase 9 (see Status.MD), plus the changes below.

### Website
- **Read-only website** (D38). Every change is made in the admin console; the server refuses any non-GET request
  (405 `read_only`). Admin page, admin password (`ECHOVR_ADMIN_PASSWORD`), repair and "Scan now" buttons removed.
- **Match page**: big tab bar with a short description per tab (Players / Timeline / Heatmap / Playback).
- **Heatmaps**: per-player layers on the match page ("Colour by: Player", side by side by default, shades of the team
  colour); new "Super fine (0.1 m)" detail on match and player heatmaps.
- **Achievements page / player achievements**: new achievements in their own "New challenges" section, grouped by
  theme, with a "Jump to new challenges" link; player profile shows a "New challenges x / 21" card.
- **Import page**: replays hidden in the console are left out of lists and counts ("N hidden" note); the failed list
  says which ones can be repaired in the console.
- Version number in the footer.

### Achievements (D39)
- Logic follows the text on the website; hidden conditions are now in the text: "(3+ minutes)" on the per-game rules,
  "(all-time average, 50+ games)" on the all-time averages, "X or more"; the page explains "use only" = 95%+ of a
  game's loadout time, "use" = 5%+, calendar days, weeks from Monday.
- Fixes: all-time averages could reach 100 % after 4 games (now need 50); unlock dates of all-time averages are exact;
  "fewer than" is strict.
- Changed targets: Pew Pew Proof fewer than **5** deaths per game (was 3); Tech Support w/RAD_Natalie **22 %** near a
  teammate in a week (was 50 %); Robot Wrecking Squad **13 %** all-time (was 20 %).
- **21 new achievements (80-100)**: unreleased gear (Starburst, Protostar, Quark, Blazar, Translocator, Dot Field,
  Forbidden Arsenal), gear mastery (all 4 weapons / ordnances / tac mods in one game), wins (5 and 10 in a row,
  Centurion, Clean Sweep 2-0, Special Delivery, Hold the Line), payload (push 3+ min, block 1+ min, push 5+ h total,
  estimated), emotes (10 in a game, 500 total). Targets checked against the 2026 archive. Overall % is now the average
  of 96.

### Stats accuracy
- Older-API hex gear symbols (e.g. `0xE32DC7C9DA8051A4` = Comet, ~490 matches) are normalised in the parser; affected
  replays are re-read once at startup, so achievements and the loadout leaderboard count them.

### Admin console (`admin.bat`, new)
- Menu or one-off commands: find players; merge / list / undo merges; challenge period; status; reprocess or repair one
  replay; repair all failed; list replays that cannot be repaired and hide / unhide them; scan the folder now; rescan
  and re-process every replay. Works on the database directly, server running or not; queued replays go first
  (`priority_replays`).

### GitHub
- `upload_to_github.bat`: uploads the application only (no replay data, database, sample replays, reference material,
  environments or build output; `.gitignore` plus a check that stops the upload if any such file is staged), each
  upload labelled with the beta version. `.gitattributes` keeps Windows line endings in the `.bat` files.

### Performance
- Achievements: per-game share caching, column loading, background refresh at startup and after imports (leaderboard
  "achievements" 21 s → instant, recent unlocks 4.2 s → 10 ms, player achievements 1.9 s → 0.5 s).
- Response cache for home, leaderboard, player profile / trends / companions / achievements, compare (keyed on the data
  stamp + a save counter); faster players list and search (0.5-1 s → <10 ms); new indexes added to existing databases at
  startup; gzip; one-minute client cache for GET requests.

### Upgrading to Beta 1
- Restart `run.bat`. On first start: new indexes are created, ~490 replays with hex gear codes are re-read in the
  background, the achievement cache is warmed. Hard-refresh the browser (Ctrl+F5).
- `ECHOVR_ADMIN_PASSWORD` is no longer used: use `admin.bat`.
