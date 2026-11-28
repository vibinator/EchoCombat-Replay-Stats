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

## 2026.11.28.16 — 13:28

- **"Close to a teammate / enemy" now means within 5 m** (user, 28 Nov: 2.65 m was "too close"): Full Team Salvo,
  Can We Talk About This?, Tech Support w/RAD_Natalie, Hug Your Frenemy, Robot Wrecking Squad and Roboticide, plus the
  "Near a teammate / enemy" stats on leaderboards, profiles and match pages. On 400 recent replays the typical share of
  a game roughly doubles (teammate 8 → 18 %, enemy 7 → 18 %). Tier numbers are unchanged for now. Lone Echo keeps
  10 m. Stats version 23: every replay is read again; until it finishes, older matches still show the 2.65 m numbers.
- **Objective time counts on the Capture Point maps only** (user, 28 Nov): what the Combat reports count as objective
  time on Fission and Surge is unknown. Camping Out on Dyson is now **Hold the Hill**: time on the objective on Dyson and
  Combustion in any 24 hours, 5 / 9 / 14 / 18 min (crown 7.6 % of the 92 Combat regulars, 4-27 Nov; was 5 / 10 / 15 /
  25 on every map). The Anomaly Doesn't Move (all time) counts the same two maps with its targets unchanged: 51 % of
  regulars have bronze (was 69 %), 1.1 % silver (was 2.2 %). The all-time total (The
  Anomaly Doesn't Move) still counts every map. Update the container; nothing to re-read.
- **Eight new challenges fill the missing periods** (user, 28 Nov, after a review of Special / One Day / Any 7 Days /
  All Time). Crown for about 7.5 % of regulars (95 with 25+ games since 1 Aug; Combat: 92 with 10+ games, 4-27 Nov):
  - Payload Rush Hour: push the payload in any 24 hours, 4 / 7 / 10 / 13.5 min
  - Payload Long Haul: push the payload in any 7 days, 6 / 12 / 20 / 30 min
  - Payload Gridlock: block the payload in any 24 hours, 0.5 / 1 / 2 / 3 min
  - Payload Blockade: block the payload in any 7 days, 1 / 2 / 3.5 / 6 min
  - Conquest of Kronos II: win games in any 7 days, 10 / 20 / 30 / 38
  - Siege of Saturn (Combat): deal damage in any 7 days, 12,000 / 20,000 / 35,000 / 50,000
  - Anomaly Watch (Combat): time on the objective in any 7 days, Capture Point maps, 10 / 15 / 30 / 40 min
  - Kronos II Day Shift (Combat): games with more kills than deaths in any 24 hours, 3 / 5 / 7 / 14
  Update the container; nothing to re-read.

## 2026.11.28.15 — 12:43

- **"Processing N replays" no longer sticks after the queue is done** (user, 28 Nov): Cloudflare kept
  `/api/overview/processing` for up to 5 minutes (edge cache), so the top bar showed "Processing 9 replays" while the
  server's queue was already empty. That answer is now `no-store` for Cloudflare and browsers, like `/api/overview/live`
  (one indexed count per visitor a minute). Update the container; nothing to re-read.

## 2026.11.28.14 — 12:31

- **Two top speeds removed by hand** (user, 28 Nov): Caprison- 42.1 m/s and Chroined 39.9 m/s, both Dyson 2023-07-17 01:32,
  both smooth runs out of Dyson's entry tubes (0 → 45-53 m/s from the tube ends at x = ±105). That match now gives them no
  top speed; the rest of their stats there stay (stats.HIDDEN_TOP_SPEEDS). Other tube runs still count: 15 of the 22 Dyson
  top speeds of 30+ m/s in the newest 422 Dyson replays are one. New home-page leaders: DinkatorBoi 37.9, JavaBava 35.6
  (regrabs mid-map), Rapollo2126 34.6. **After the update** that one replay needs reading again (admin console: reprocess
  `dyson/[2023-07-17 01-31-59] 6439ECE9-….echoreplay`); no stats version change, no full re-read.
- **Pinned challenges say what is left to complete** (user): next to "x % of the way" on a pinned card, e.g. "40 more games
  to complete" or "3.2 m/s more in one game to complete", counted to the crown (the last tier).
- **Flag on a profile says the country and the region** (user): "Jersey - Europe" next to the flag instead of only "Europe"
  (player page and My profile).

## 2026.11.28.13 — 12:21

- **Flamingo Challenges panel is smaller** (player page and My profile): about 115 px tall instead of 185, with a smaller
  button, headline and bar, and each tab's count on one line.

## 2026.11.28.12 — 12:04

- **Flamingo Challenges panel: "View all Flamingo Challenges" is on the left** (player page and My profile); on phones
  it is at the top of the panel.

## 2026.11.28.11 — 12:03

- **Challenges page: a big "View my challenges" button** at the top, for the logged-in player (with a link to their
  player page beside it); hidden on their own challenges. Not logged in, it says "See your own challenges: log in with
  Discord"; a Discord account not linked to a player yet gets a button to My profile.

## 2026.11.28.10 — 11:58

- **The game region follows the country.** Every country has its own game region (the nearest servers: Europe, Japan,
  Singapore, Australia, or US East / Central / West for the Americas), picked for you. Only United States and Canada
  players choose, and they see just East, Central and West. A region that does not match the country is never kept.
- **Flamingo Challenges panel on My profile too,** with the same big "View all Flamingo Challenges" button as the
  player page; the panel is now titled Flamingo Challenges.

## 2026.11.28.9 — 11:48

- **Profiles: flag and game region.** Players can pick their country (shown as a flag beside their name) and their game
  region (US East, US Central, US West, Europe, Japan, Singapore, Australia) in Edit profile, on their player page or
  My profile. Flags are pictures, so they show on Windows too.
- **Detected automatically until picked.** For a player who has not picked one, the country comes from their connection
  when they visit the site logged in (Cloudflare's country, no IP address kept), with the nearest game region; it shows
  with a small "detected" tag. Picking one by hand always wins and is never overwritten; "Set them from my connection"
  turns detection back on. US and Canada get the flag only, unless Cloudflare's visitor location headers are on.
- **Player page: Challenges as one big area.** The one-line Challenges row is now a large panel: how many are fully
  complete with the bar, how far along each tab is (Specials, One Day, One Week, Cumulative), and a big "View all
  challenges" button.

## 2026.11.28.8 — 11:13

- **Challenges: Edit your Bio counts.** It was the last challenge left out of the totals: a player with a bio saw it
  "Completed!" but "0 of 184 challenges fully complete" at the top. It now counts like every other challenge: in
  "challenges fully complete" (185 in all), the overall %, the ranking and Medal Collector. Every challenge now counts.
- **Fixed: the Bio card now follows the bio the page shows,** also for merged players (it looked only at the exact id).

## 2026.11.28.7 — 08:55

- **Challenges: your best on the card.** The card a challenge opens on a player's page now shows their best so far
  ("Your best game: 185 s", "Your best 24 hours", "Your best 7 days", or "Your total" for all-time ones), also once the
  challenge is completed. Won-or-not challenges have no number, so they show none.

## 2026.11.28.6 — 00:52

Most of this went out early in the second 2026.11.28.5 commit (00:50), which picked up the work in progress; these notes
cover all of it.

- **Every challenge counts 2v2 and up** (user, 28 Nov). Only games where both teams had at least 2 players for at least
  half of the match count, for every challenge: Specials, One Day, One Week and Cumulative alike. Full Lobby keeps its 5v5.
  - Before, the Specials and the win / Payload challenges needed 3+ per team, and the rest had no minimum: 1v1 and solo
    lobbies counted for them.
  - Every card now shows "2+ players per team".
  - Targets unchanged (user: "don't change the tier numbers, only the 2v2 rule"). On the local archive since 1 Aug
    (111 regulars), most crowns move by under 3 points. The biggest moves: Payload Pedal to the Metal 10.8 -> 22.5 %,
    Pew Pew Proof and Four-Map Tour 8.1 -> 13.5 %, Checkpoint Reached 8.1 -> 1.8 %, Combat on Quest When? 8.1 -> 2.7 %,
    Blast Furnace 6.3 -> 2.7 %.
  - Since 1 Nov, 35 % of matches had a team under 2 players and 23 % were exactly 2 on the smaller team.
  - No re-read needed; the challenge answers rebuild after the update.
- **Payload Pedal to the Metal and Payload Roadblock are back in Specials** (user, 28 Nov: Capture Point has Contested
  Point, Payload had nothing). Longest push / block in one game, with the targets they had (push 100 / 140 / 175 / 205 s,
  block 22 / 45 / 60 / 70 s). They were retired on 26 Nov as repeats of the all-time totals, but one game is not the
  all-time total. Challenge total +2.
- **One Day is now any 24 hours** (user, 28 Nov). Every day challenge, replay and Combat, counts your best 24 hours in
  a row, starting at any of your games, like "any 7 days" does. Before, it was the UK calendar day, so a session across
  midnight UK (most play is 22:00-03:00 UK) was cut in two.
  - The tab is still "One Day", with an ⓘ button in its corner: "In any 24 hours: your best 24 hours in a row count,
    starting at any of your games ..." (user, 28 Nov). One Week has one too ("In any 7 days ..."). Hover shows the text, and
    a tap opens it under the tabs, so it works in VR. The cards say "Best 24 hours" and the descriptions "in any 24 hours".
  - Targets unchanged, apart from the two below. On the local archive (95 regulars since 1 Aug), the day crowns rise by
    2.7 points on average: a 24-hour window can hold two sessions. The volume ones rise most: Point Captured 4 -> 13 %,
    Constant Contesting 5 -> 12 %, Damage Control 28 -> 40 %. The skill ones barely move.
  - No re-read; the challenge answers rebuild after the update.
- **Kill Spree Bot and Helping Hands of Kronos II harder** (user, 28 Nov: crowns around 10 %): the easiest challenges
  outside gear after the change (crowns 18.5 and 17 %).
  - Kill Spree Bot: 20 / 85 / 115 / 135 kills (was 20 / 45 / 65 / 100).
  - Helping Hands: 25 / 105 / 125 / 140 assists (was 25 / 55 / 80 / 120). Assists stay above kills at every medal.
  - Reached by 19.6 / 17.4 / 9.8 % and 21.7 / 15.2 / 10.9 % of the 92 Combat regulars (10+ games, 4-26 Nov) at
    silver / gold / crown.
- **Pew Pew Proof, Four-Map Tour and Payload Roadblock harder** (user, 28 Nov: crowns "around 10 %"): the next easiest
  outside gear (crowns 15.8 % each). Measured on the 95 regulars (25+ games since 1 Aug, 2v2 rule); bronze unchanged.
  - Pew Pew Proof: 5 / 20 / 25 / 35 games in a row (was 5 / 10 / 15 / 25), reached by 63 / 23 / 16 / 9.5 %.
  - Four-Map Tour: 1 / 8 / 13 / 18 wins on every map (was 1 / 3 / 7 / 12), 92 / 26 / 15 / 9.5 %.
  - Payload Roadblock: 22 / 60 / 70 / 90 s (was 22 / 45 / 60 / 70), 74 / 21 / 16 / 9.5 %.
- **Payload Pedal to the Metal harder** (user, 28 Nov): 100 / 210 / 225 / 240 s for bronze / silver / gold / crown (was
  100 / 140 / 175 / 205). Under the 2v2 rule the old ones were reached by 88 / 65 / 47 / 24 % of the 95 regulars (25+ games
  since 1 Aug on the local archive); the new ones by 88 / 20 / 13 / 6 %, in line with the target policy.
- **Flawless Chassis has medals** (user, 28 Nov): kills in one game without dying, bronze 5, silver 8, gold 10, crown 12.
  It was a single crown for 10+ kills, which is now gold. In the combat reports (4-26 Nov, 92 regulars with 10+ games),
  25 / 10 / 7 / 3 % reach them; the crown should get close to 7.5 % over the challenge period.

## 2026.11.28.5 — 00:30

- **Lobby Mime Troupe and Showbot say that emotes count anywhere** (user, 28 Nov: they "are allowed to be done out of
  bounds and inside the war room"). They already did: every frame of the game is counted, before any bounds check
  (stats/player.py), war room and load-in spot included. The cards now have a note saying so.

## 2026.11.28.4 — 00:28

- **Lone Echo crown 87.5 %** (user, 28 Nov): bronze 70 %, silver 75 %, gold 80 %, crown 87.5 % at 10 m (85 % in
  2026.11.28.3). The crown is reached by 11 % of regulars in the local recent replays (17 % at 85 %). Same deploy and
  re-read as 2026.11.28.1.

## 2026.11.28.3 — 00:27

- **Lone Echo crown 85 %, evenly spaced** (user, 28 Nov: "so it looks more even"): bronze 70 %, silver 75 %, gold 80 %,
  crown 85 % at 10 m (crown was 88 % in 2026.11.28.2). The crown is reached by 17 % of regulars in the local recent
  replays (was 10 %), more than the 7.5 % policy: the user's choice for even steps. Same deploy and re-read as 2026.11.28.1.

## 2026.11.28.2 — 00:26

- **Lone Echo slightly easier** (user, 28 Nov): bronze 70 %, silver 75 %, gold 80 %, crown 88 % at 10 m (was 75 / 80 /
  85 / 90 in 2026.11.28.1), reached by 68 / 48 / 27 / 10 % of regulars in the local recent replays. Same deploy and
  re-read as 2026.11.28.1.

## 2026.11.28.1 — 00:22

- **Lone Echo counts teammates within 10 m, with lower targets** (user, 28 Nov: 3.5 m was too close, "10 meters, but
  a lower precentage").
  - At 3.5 m nearly everyone was far enough nearly all game, so the tiers sat at 95-99.5 % and a few seconds next to a
    teammate decided them.
  - New targets: bronze 70 %, silver 75 %, gold 80 %, crown 88 % of the in-bounds time more than 10 m from every
    teammate (was 95 / 98 / 99 / 99.5 %). First set at 75 / 80 / 85 / 90, then made slightly easier (user, 28 Nov).
  - Measured on the 1,657 local recent replays (130 regulars, 4+ minute 3v3 games), these are reached by 68 / 48 / 27 /
    10 % of regulars (75 / 80 / 85 / 90 would be 48 / 27 / 17 / 8 %). The same pass at 3.5 m on the old targets gave
    51 / 21 / 11 / 8 %, in line with the live numbers.
  - A typical game is 46 % at 10 m.
- **Stats version 22: every replay is read again after the update** (hours on the NAS); the site keeps its stats
  meanwhile (D57).
  - Lone Echo's count from an older read is set to empty at startup (db._forget_old_lone_echo, 0.2 s on the local
    archive), so the old 3.5 m numbers can never give a false medal against the lower targets.
  - Lone Echo fills in again as each replay is read. "Near teammates" (2.65 m) is unchanged.

## 2026.11.27.23 — 23:46

- **The Combat challenges count** (user, 27 Nov: "Make Combat count"). They were provisional since 5 Nov (out of every
  total). Now they count like the rest:
  - in "X of Y challenges fully complete" and the average progress;
  - in Top players and the challenges leaderboard;
  - in Medal Collector (a ladder from silver on, an award card when won).

  JavaBava went from 2 / 134 to 7 / 182. They still come only from the recorder's match reports and are cached apart
  from the replay ones, only added together when shown (profile_achievements.counted_answer / with_league, like the
  George League cards). A player with Combat reports but no replay game in the period joins the ranking, merged ids
  once. New reports reach the ranking within 5 minutes. Changing a Combat target from now on moves people's tiers and
  totals. The page texts that said Combat does not count are updated.
- **Echo Streak (Wins): crown an even 10** wins in a row (user, 27 Nov), was 9. Bronze 3, silver 5, gold 7 unchanged.
- **I Use All the Loadouts: crown 100** loadouts (user, 27 Nov), was 75. Bronze 5, silver 25, gold 50 unchanged.
- **Kill Spree Bot and Spontaneous Combustion stay as they are** (user, 27 Nov). On the local reports (4-27 Nov, 92
  players with 10+ games) Spontaneous Combustion's crown (8 top-kill games in one day) is reached by 7 %, on the 7.5 %
  policy.
- **Mega Prizes on a merged player's page** (user, 27 Nov: echofox's page, /challenges/echofox/341, showed 0 Combat
  matches while the Mega Prize list had them at 9). Their match-list account is linked to the Discord-id player merged
  into 341, and the page only looked for accounts linked to 341 itself. It now looks at every merged id (api/arena.py
  player). The Echo account line on the profile had the same gap (api/profiles.py _account). Needs the update deployed.

## 2026.11.27.22 — 23:34

- **Top players on /challenges has no minimum of games** (user, 27 Nov: "shouldn't have a min, just the top players
  with the most amount of challenges won"). It needed 10 games inside the challenge period, so it stayed empty for the
  first hours of a period (2026-11-27: the most anyone had was 9). Still ranked by challenges fully complete, average
  progress breaking ties. The stats leaderboard's own minimum is unchanged.

## 2026.11.27.21 — 22:36

- **The challenge period is back on /challenges, in small text next to "All challenges"** (user, 27 Nov): start → end (or "open-ended"), on the viewer's clock; hover text says only matches inside it count. Hidden until a start date is set.

## 2026.11.27.20 — 22:26

- **"5th Loadout when? "Soon™"" is now "I Use All the Loadouts"** (user, 27 Nov: there are more than 5 loadouts now).
  Same challenge (id 67), same targets.
- **It lists every loadout you have not used yet** (user, 27 Nov: "show the player which combination hasn't been used
  yet"). Under "Try next" a folded line "N loadouts not used yet" opens a list per weapon: each ordnance with the tac
  mods still to use with it (for example "Pulsar · Detonator: Threat Scanner · Energy Barrier · Overcharge"). A loadout
  counts as used after 1 minute with it, as before. Shown on both the list and the grid view of the card until the
  challenge is complete.
- Needs the update deployed. Because the challenge code changed, the challenge ranking is worked out once from scratch
  after the restart (a few minutes on the NAS).

## 2026.11.27.19 — 22:20

- **The Mega Prizes heading line shows only the start too** (user, 27 Nov): "From 2026-11-27 21:20 · Delta-13 ..."
  instead of "2026-11-27 21:20 → 2027-12-27 · ...". 2026.11.27.18 changed only the box under it. The Console still
  shows both dates.
- **The green recording dot in that line sits beside "recording"** (user, 27 Nov): it was drawn before the " · ", right
  against the top player's match count.
- **The Echo Combat Mega Prize card says it is time-limited** (user, 27 Nov: "include that there is a time period"): a
  first line "Time-limited: only matches played inside the Mega Prize period count." on the Delta-13 card and in a
  player's Mega Prizes row. No end date is shown.
- Needs the update deployed (frontend only).

## 2026.11.27.18 — 22:15

- **Challenge cards on a phone** (user, 27 Nov: the cross sometimes did not show, and cards stacked up). Only one card
  is open at a time: opening another closes the last, and a tap anywhere outside the card closes it (with a mouse too).
  On touch screens a card shows only when tapped open, so it always has its cross; a hover or focus left over from an
  earlier tap no longer shows a second card without one.
- **The Mega Prizes box on the Challenges page shows only the start** (user, 27 Nov: "only mention the starting time,
  not the end time"): "From 2026-11-27 21:20 · Only matches played from then on count for Mega Prizes." The end date
  still applies.
- Needs the update deployed (frontend only).

## 2026.11.27.17 — 22:08

- **The Echo Combat Mega Prize (Delta-13) counts 2v2 games** (user, 27 Nov: "for ONLY the combat mega prizes"). A
  Combat match on the live match list now counts once both teams have 2+ players (or 6+ players are seen), and the
  replay-file history before the live count counts matches with 2+ per team for half of the match. The Arena Mega Prize
  (Jack Series 11) keeps 3v3. The prize card says "at least 2v2".
- The replay-file history is recounted at once. Live matches that were too small before this update were never
  recorded, so they cannot be added; 2v2 matches count from the update on.
- Needs the update deployed.

## 2026.11.27.16 — 22:00

- **The five George League challenges now count as full challenges** (user, 27 Nov: "make it count as a full
  challenge"). A won card adds to "X of Y challenges fully complete", the average progress, the Top players ranking and
  the challenges leaderboard, and counts as one more challenge for Medal Collector. The total goes from 129 to 134 for
  everyone. The cards reach the ranking within 5 minutes of the hourly league read. Edit your Bio and the Combat
  challenges stay out of the totals as before, and the recent-medals feed still lists replay and Combat medals only.
- **Combat challenges count 2v2 games** (user, 27 Nov: was 3v3 and up). A recorder report counts when both teams had 2+
  players for at least half of the match (and the player was there 4+ minutes). Their cards say "2+ players per team".
  The replay challenges keep 3+ per team (the Delta-13 Mega Prize too, until 2026.11.27.17).
- **Two period notes removed** (user, 27 Nov): the challenge-period box ("<start> → <end>. Only matches played inside this
  period count for challenges; the player stats pages count every match") is gone from the Challenges pages, and the
  line "Only matches inside the Mega Prize period count: <start> → <end> (recording). No game account is linked to this
  player yet." (and the same hover text) is gone from a player's Mega Prizes row. The period still applies; the
  preview-only note before the launch and the period box in the Mega Prizes section stay.
- Needs the update deployed. Nothing is re-read; the Combat challenges are rebuilt from the reports at the first look.
  Because the challenge code changed, the challenge ranking is worked out once from scratch after the restart (a few
  minutes on the NAS, the previous one is not reused).

## 2026.11.27.15 — 19:53

- **Public player-stats API** (user, 27 Nov: "open up an API for player stats", with API keys and profile stats only).
  `GET /api/v1/players?q=<name>` finds players, `GET /api/v1/players/<id>?period=&map=` gives one player's profile
  stats (games, wins / losses, deaths, speeds, time near teammates, payload, emotes, per map and period). No heatmaps,
  bios, Discord ids, pings or match lists; stats hidden from players stay hidden. Each key may ask 30 times a minute and
  1,000 times an hour. The answers are JSON, and the API itself is listed as JSON at `/api/v1/openapi.json` (OpenAPI,
  no key needed). The rest of `/api/` still answers only the site's own pages. Details: docs/API.MD.
- **API keys from the Console** (user, 27 Nov: "let an Admin get an API key / URL from the console"): a new API tab
  with New API key (shows the key and a ready-to-use URL once), List API keys and Revoke an API key. Admins only.
  Also `admin.bat api-key-add <name>`, `api-keys`, `api-key-revoke <id>`. Only a hash of each key is stored, and the
  audit log blacks the key out.
- After the update: make a key and try it from a script. Cloudflare's Bot Fight Mode may challenge scripts before they
  reach the server; if a script gets a Cloudflare page instead of JSON, Bot Fight Mode needs turning off (docs/API.MD).

## 2026.11.27.14 — 19:40

- **Lobby Mime Troupe counts every game** (user, 27 Nov: "one is for playing a game, it shouldn't be tied to your
  death"). It is now the emotes you use in one 4+ minute game, win or lose, whether you die or not (it was a game in
  which you never die). Showbot stays the one for a game your team wins. Targets unchanged: 8 / 24 / 32 / 40.
- **King/Queen of Pubs crown at 1,000 pubs** (user, 27 Nov): 50 / 250 / 500 / 1,000 (was 39 / 140 / 250 / 290).
- **Rounder challenge targets** (user, 27 Nov: "more pleasing numbers"). Count targets moved to the nearest round number
  (5s, 25s, 100s), with each tier close to where it was: e.g. King of the Hill / Feed the Flamingo 20 / 75 / 125 / 150
  (was 20 / 75 / 130 / 150), the four map ladders 10 / 40 / 60 / 75 (was 12 / 40 / 60 / 74), 5th Loadout when?
  5 / 25 / 50 / 75 (was 7 / 27 / 54 / 78), Lobby Regular 20 / 25 / 35 / 45 (was 18 / 26 / 35 / 46), Capture Point Clean
  Sweep 2 / 20 / 25 / 30 (was 2 / 18 / 26 / 32), Payload Delivered 1 / 10 / 15 / 20 (was 1 / 11 / 18 / 21). 28
  challenges and 19 Combat challenges in all; each one's old targets are in the code beside the new ones. Averages
  (%, m/s) and small day / week counts kept their tuned values. In Combat, assists stay above kills (crown 3,500 assists
  vs 3,000 kills; 425 vs 375 in 7 days; 120 vs 100 in a day).
- **Mega Prize pictures go full screen**: a ⛶ button beside the zoom buttons. Zoom and drag work there too; Esc or ✕
  leaves.
- **Leaderboard**: the "new" mark beside players not ranked in the previous period is gone. **Challenges**: the "Full
  leaderboard" link beside Top players is gone.
- Restart needed (the challenge rules are read at start-up); no re-read of replays.

## 2026.11.27.13 — 15:40

- **Arena Mega Prize counts the older Arena matches again** (user, 27 Nov: "Stoner should have way more between
  2026-10-31 → 2027-12-27"). Arena matches counted before today's update lost their dates (they were deleted after
  2 days), so a period moved earlier found only the last few days. Each player's undated matches (their running total
  minus the dated ones, played from 4 Nov, when Arena counting began, to about 25 Nov) are now added when the Mega
  Prize period starts on or before 4 Nov and does not end before the dated history begins. A later start still counts
  only dated matches, because which of the undated ones fall inside it cannot be known. Applies to the cards, top 10,
  closest players, search, profile row and the Console winners report.

## 2026.11.27.12 — 15:18

- **Start time for the challenge and Mega Prize periods** (user, 27 Nov: "let me set a starting time … a time and
  date"). The Console's "Launch date and challenge period" and "Mega Prize period" have a new optional **Start time**
  box (UK time, the clock match times use); `admin.bat challenge --start "2027-01-01 18:00"` and `mega-period` take it
  too. Without a time the period starts at 00:00 as before. The launch ("Coming soon" ends), which matches count for
  challenges and Mega Prizes, the Arena/Combat Mega Prize totals, the "recording" dot and the Console's status all
  follow that minute. The end date stays a whole day. The website shows the start in the viewer's own timezone.
- **Mega Prizes:** removed the note "Arena history only starts on 2026-11-04, so totals are lower than Combat."

## 2026.11.27.11 — 15:08

- **Arena Mega Prize follows the Mega Prize Period** (user, 27 Nov: "the number should reflect FROM the data picked from
  the mega prize period"). The Arena count was a running total that only went up, so changing the dates did nothing.
  It is now counted from the saved Arena matches inside the period, like Combat: changing the dates in the Console
  recounts at once (the 10-minute Mega Prize cache is keyed on the period). Used by the Mega Prizes cards, top 10 with
  the change over the last day, closest players, search, a player's profile row and the Console winners report.
- **Arena match history kept for good.** Counted Arena matches were deleted after 2 days; they are now kept, like
  Combat's. Matches are recorded all the time, inside the period or not, and the period only filters them, so moving the
  start date earlier picks up matches already played. Applies to the Combat Mega Prize recording too.
- Arena matches counted before this update are gone (only the last 2 days of them were still saved), so Arena Mega
  Prize counts start from what is still in the database. The old all-time per-player totals are kept but no longer
  shown as the prize count.
- Console: the Arena counter reads "Recording" outside the period (it used to say the list was not being read);
  `admin.bat mega-period` says both prizes use the new dates straight away.
- The poller remembers only the last 2 days of counted matches in memory (the history stays in the database), so it
  doesn't grow over a long uptime.
- The code for this went in with 2026.11.27.10 (committed alongside another change); this entry describes it.
- Needs the update deployed (backend + frontend); nothing is re-read.

## 2026.11.27.10 — 15:05

- **Player profile: Mega Prizes open by default** (user, 27 Nov). The Mega Prizes row on a player's Challenges profile
  now shows the prize cards (pictures, prize, what counts, progress) straight away; "Less ▴" still closes it.
- Needs the update deployed (frontend only); nothing is re-read.

## 2026.11.27.9 — 14:35

- **Challenges page: tighter spacing** (user, 27 Nov). Less space above "Top players" / "Recent tiers reached" and above
  "All challenges" (1-1.25 rem instead of 2 rem), and "Full leaderboard" now lines up with its heading.
- **Top players and Recent tiers reached cards fit their content.** The fixed 8.5 rem card height is gone: every card in
  both panes is now as tall as the tallest card's text, so the two rows line up without an empty band under short cards.
- Needs the update deployed (frontend only); nothing is re-read.

## 2026.11.27.8 — 13:06

- **Busy profiles' challenges load at once** (user, 27 Nov: Vibinator's Challenges page, 7,700 games, took 25-60 s on the
  NAS). Working out a player's challenges takes ~6 s on the dev PC for such a history; the answer was kept only in memory
  and rebuilt after every restart, every midnight, and whenever other pages pushed it out. Now, like the long heatmaps:
  - kept on disk (`data/cache/answers`, 7 KB for that player; read back in under a millisecond), so a restart keeps it;
  - built again only when that player has a new or re-read match, or the challenge rules change, never at midnight or
    for other players' replays (and then the saved one is still shown while the new one is built);
  - the idle pass builds the challenges of the 200 most active players ahead of time after a start (before their
    heatmaps), so even their first look after an update is instant.
  - The answer is still the same for every visitor, so Cloudflare keeps it once challenges are public (tested).
- **Review fixes (27 Nov, end-to-end review + two cloud reviews):**
  - **"Challenges not showing" on a player page, found:** the page gave up on any answer after 30 s, and a busy player's
    challenges took longer on the NAS (measured live: both tries cut off at 30.0 s, the row never appeared). Challenge
    answers now get the 90 s limit heatmaps have, and the Challenges row / tab say "Working out this player's progress…"
    while it is built instead of being missing.
  - The saved challenges are only built again when the matches that count change (duplicate copies included), a damaged
    saved file is built again instead of failing every request, an out-of-date answer is marked STALE (Cloudflare does
    not keep it, the page asks again), and an answer the idle pass already saved is not built a second time.
  - **Cloudflare:** pins now ride in the shared challenges answer (only a logged-in visitor asks for their own); a
    player's bio for visitors who are not logged in comes from a new shared `/api/players/{id}/bio` that Cloudflare keeps;
    the shared `/api/challenges` says whether the Mega Prizes are public, so visitors who are not logged in no longer ask
    the per-visitor `/api/arena/visible`. An anonymous player page view went from 2 requests that always reach the NAS
    (bio, Mega Prize check) to none; only the login check every page makes is left.
  - Pins: viewing a player no longer takes the database's write lock (it only writes when a pinned challenge is complete).
  - Merges: a hidden win-loss stays hidden whichever record is kept, also for ids merged before, and after an undo.

## 2026.11.27.7 — 12:47

- **Pin challenges to work on** (user, 27 Nov, D68). Logged in with Discord, a player pins up to 3 challenges with the new
  pin button on a challenge row or in its opened card. Everyone sees them: a **Pinned** row on the player page (name, bar,
  count toward the next tier) and **Pinned** cards above Your next tiers on their Challenges page. A completed pin removes
  itself. Only the account that can edit the player's bio can change pins.
- **Edit your Bio now counts a bio written on My profile** for players without a bot link (the bio is kept by Discord id;
  the challenge only looked at bot-linked profiles, so it never completed for them). Its rarity counts those bios too.
- **A merge always keeps the record seen most recently** (user, 27 Nov). Whichever record is named as the one to keep
  (Console, admin.bat), the one with the latest "last seen" becomes the main record and the others are merged into it; a
  record already merged into another counts as that player's whole group. The console says which record is kept, the
  merge suggestions put that record first, and pinned challenges follow the merged records to the kept one. Existing merges
  are not changed.
- After the update: restart the server (new table `challenge_pins`, created by itself).

## 2026.11.27.6 — 12:38

- **Mega Prizes "More" button on the left** (user, 27 Nov): on a player page the Mega Prizes row's More / Less button now
  sits just after the "Mega Prizes" label, like View all on the Challenges row, instead of at the far right.

## 2026.11.27.5 — 12:27

- **Showbot and Lobby Mime Troupe twice as hard again** (user, 27 Nov: an emote takes 2-4 s and has no cooldown, so a
  4+ minute game has room for 60-120). Lobby Mime Troupe 8 / 24 / 32 / 40 emotes in a game without dying (was 4 / 12 / 16 /
  20), Showbot 16 / 24 / 28 / 32 emotes in a win (was 8 / 12 / 14 / 16). Past play stays far below that (Showbot's record
  18, Lobby Mime Troupe's best since 1 August 11), but both need only deliberate play, so every tier stays reachable.
- Needs the update deployed (restart); nothing is re-read, medals are worked out from the saved emote counts.

## 2026.11.27.4 — 12:24

- **Home: the rules of "Top 5 fastest players" are on the page** (user, 27 Nov: why DinkatorBoi and JavaBava are not
  higher). Under the cards: "Each player's best game · only games of 2+ minutes with 2+ players on each team"; the ⓘ by
  the heading (and each card's hover) gives the full speed rules: fastest average over one second by the distance
  travelled, regrabs and shooting backwards count, instant solo launches, readings over 100 m/s, frozen players and clock
  jumps do not.
- Why they stay at 37.89 / 37.71 m/s (user chose to keep the rule): their 47-49 m/s regrab flights (Dyson, 26 Nov, live
  matches 326076 and 326078) were practice games of 0 v 2 and 1 v 2, which do not count; the leaderboard and Records
  leave them out the same way. The 2026.11.26.13 note below gave a top 5 worked out without that rule; corrected there.
- Needs the update deployed (frontend only); nothing is re-read.

## 2026.11.27.3 — 11:56

- **Five new Specials for the Echo Combat George League, Rookie League only** (user, 27 Nov: the Varsity League is
  ignored), in their own "George League" box on the Specials tab:
  - **Join Echo Combat George League**: be on a Rookie team (now or before) or the Rookie leaderboard.
  - **Join a George League Team**: be on a Rookie team's roster (a former member counts too).
  - **Play a George League Match** / **Win a George League Match**: one Rookie match played / won, this season or an
    earlier one.
  - **Join as a George League Sub**: the League Sub role, and allowed to play in Rookie (not a veteran, or given an
    override; the role itself is shared by both leagues).
- The server reads the Rookie League from ecgleague.com every hour (user: 6 hours was too long; the first read a minute
  after it starts): the player list, the player leaderboard, the team list and each team's roster, about 10 requests,
  one a second. The site serves both leagues at the same addresses; the `X-ECGL-League: rookie` header picks Rookie.
  Earlier Rookie seasons are read once per leaderboard player from their own page. Players are matched by their Discord
  account (a bot / admin link, a player whose id is the Discord id, or an Echo account seen on the match list). Only the
  Discord ids and the date each thing was first seen are kept (new table `league_members`, kept across rebuilds). Once
  done they stay done, even if the player leaves later. Like Edit your Bio they are won or not, and stay out of totals,
  the ranking and Medal Collector.
- On 27 Nov the Rookie League had 6 teams, 18 players (17 on a team), 12 League Subs allowed in Rookie, and no matches
  played yet: Play and Win fill in once its season starts.
- Needs the update deployed (Recreate); the table is made at the start, and the cards fill in after the first read.

## 2026.11.27.2 — 10:20

- **Mega Prizes are counted at most every 10 minutes** (user, 27 Nov: slow again; "not super important to be
  real-time", fewer live requests to the NAS the better). The Challenges page's Mega Prizes, a profile's Mega Prize
  row and the Mega Prize search share one count that the server keeps for 10 minutes, so most visits answer at once
  instead of recounting every player's matches. Changing the Mega Prize period in the Console counts again straight
  away; who may see the prizes is still checked on every request.
- The pages also keep these answers while you browse (as the rest of the site does): going back to the Challenges page
  shows them at once and asks the server again only after a minute, in the background. They stay out of Cloudflare and
  the browser's storage, as before.
- Needs the update deployed (Recreate in Container Station).

## 2026.11.27.1 — 09:55

- **Player challenges tab: "Sort by closest to the next medal" removed** (user, 27 Nov). "Your next tiers" at the top
  already lists the closest ones; the grouped list is the only view now.
- **"Jump to new challenges ↓" link removed** from the Challenges page and the player tab (user, 27 Nov). Links to
  `…#new` from other cards still scroll to the new challenges.
- **Mega Prizes on a player's profile open up** (user, 27 Nov): a **More ▾** button under the one-line progress row
  shows both prize cards with the front/back pictures (zoomable), the prize, what counts and this player's count.
  Closed by default.
- **Player profile: the Challenges row's "View all →" button sits on the left** now, right after the "Challenges"
  label, before the count and the tier bar (user, 27 Nov).
- **Challenges page: smaller "Top players" and "Recent tiers reached" cards** (user, 27 Nov: too much padding and
  words). Top players: rank, player, "51 / 129" (fully complete) and "255 tiers"; silver-or-better, best category and
  average progress are hover text. Recent tiers: date, player, challenge and the tier chip; the rule is hover text. The
  cards are about half as tall (minimum 8.5rem instead of 19rem).
- **A player's Challenges page header has one link: "← Player profile"** (user, 27 Nov). "All challenges" is gone
  from there; the site menu still has Challenges.
- **Mega Prizes load faster on the Challenges page** (user, 27 Nov: took a long time). `/api/arena/progress` counted
  every player's Combat matches (live list plus replay history) four times per request; it now counts once for now
  and once for a day ago, and the closest players and the winner count reuse that. Same numbers, nothing cached.
  Needs the backend restarted (deploy).

## 2026.11.26.31 — 23:09

- **"Overclocked" is now "Overcharged"** (user, 26 Nov): the Overcharge Veteran (games using Overcharge, Cumulative). Same id,
  targets and progress.

## 2026.11.26.30 — 23:05

- **A short hint under every challenge name** (user, 26 Nov: names kept, but clearer at a glance). Each row shows a few grey
  words saying what it is: "Only Detonator, in a day", "Fission games, in 7 days", "Games with Pulsar", "Close to teammates,
  in 7 days", "Win the MVP card in one game" ... built from the rule, written by hand where the rule would be cut short.
- **"Techneium-99" is now "Meltdown on Fission"** (user, 26 Nov): the One Day Fission challenge. Same id, targets and progress.

## 2026.11.26.29 — 23:01

- **No category tags in challenge names** (user, 26 Nov: "now that the challenges are organised, you don't need to put
  (weapon) etc in the title"). "(Weapon)", "(Ordnance)", "(Tac Mod)", "(Payload)", "(Capture Point)", "(Emotes)",
  "(Movement)", "(Activity)", "(Wins)", "(Loadout)", "(Map)", "(Combat)" and "(Award card)" are gone; the tabs and topic boxes
  say it. The names themselves stay. Award cards are now flagged by the server ("award") instead of by their name.
- **"Your next tiers" says how to get there** (user, 26 Nov). Each card now shows the goal for the next tier ("Play 5 games
  using only Stun Field in any 7 days"), where it has to happen with the player's best so far ("Within any 7 days: reach 5.
  Your best 7 days so far: 4." / "4 more: everything in the challenge period adds up."), and the conditions a game must meet
  (4+ minutes, 3+ players per team, "only" = 90 %+ of the game, games on 3 different days from silver).

## 2026.11.26.28 — 22:58

- **Cumulative targets raised for November's activity** (user, 26 Nov: "let's say November activity holds"; November has
  about twice the games of the months before).
  - Gear Veterans (all gear): 20 / 50 / 80 / 120 games (were 15 / 35 / 55 / 80).
  - The other count-based Cumulative ladders went halfway between their 4-month targets and November's pace (safe if
    activity drops back): My Other Chassis Is a Toaster 7 / 22 / 43 / 64, 5th Loadout when? 7 / 27 / 54 / 78, Pixel Party!
    95 / 400 / 800 / 1,400, King of the Hill and Feed the Flamingo 20 / 75 / 130 / 150, the four map ladders 12 / 40 / 60 / 74,
    King/Queen of Pubs 39 / 140 / 250 / 290, Capture Point Clean Sweep 2 / 18 / 26 / 32, Payload Shutout 2 / 15 / 20 / 27,
    Payload Freight Train 5 / 23 / 38 / 53 min, Lobby Dance Floor Legend 38 / 120 / 150 / 230, Lobby Regular 18 / 26 / 35 / 46
    days, Loyal Bot 7 / 10 / 12 / 15 weeks, Time Well Wasted 5 / 19 / 30 / 36 h, Overtime on Kronos II 9 / 26 / 36 / 43, Point
    Taker 8 / 29 / 40 / 53, No Gun Left Behind, Forbidden Arsenal and Loadout Scholar Bot 2 / 5 / 9 / 15, Nothing Leaves
    Kronos II 4 / 11 / 14 / 17 min, Capture Point Comeback 2 / 12 / 17 / 19, One-Trick Pony 3 / 16 / 29 / 50.
  - Streaks (Echo Streak, Ready Every Dawn), averages and the already-hard ones (Versatile Bot, Four-Map Tour, Payload
    Delivered) stay.

## 2026.11.26.27 — 22:40

- **One Week "only <item>" targets rounded: 5 / 10 / 15 / 20 games** (user, 26 Nov: "more even looking, with the top being
  20"), the same for every weapon, ordnance and tac mod (were 3 / 10 / 14 / 18). Over the last 4 months: Repair Matrix /
  Detonator 37-40 / 27 / 18-19 / 13 %, the typical item's crown 4 %. Bronze (5 games) still needs no spread; silver and up need
  games on 3 different days (the no-spread limit moved from 4 to 5 games with it).

## 2026.11.26.26 — 22:36

- **"I've Got a Fever, and the Only Prescription Is Pew Pew Pew!" is now "Combustion Chamber"** (user, 26 Nov): the One Week
  Combustion challenge (games on Combustion in any 7 days). Same id, targets and progress.

## 2026.11.26.25 — 22:33

- **Super Ultra Hyper Turbo a tiny bit easier** (user, 26 Nov): 19 / 24 / 29 / 35 m/s (was 19 / 24 / 30 / 37). Bronze and
  silver unchanged; of the 125 regulars in the newest local replays 54 / 10 / 3 / 2 % reach each tier (crown was 1 %).

## 2026.11.26.24 — 22:19

- **Cumulative challenges set for the 4-month challenge period** (user, 26 Nov). Measured on the last real 4 months of matches
  (27 Jul-26 Nov, 255 regulars): most Cumulative ladders already land at a 2-6 % crown and stay. Changed:
  - Made reachable (nobody could finish them in 4 months): Versatile Bot 1 / 2 / 3 / 4 days (was 1 / 5 / 13 / 23); No Gun Left
    Behind, Forbidden Arsenal and Loadout Scholar Bot 1 / 3 / 6 / 10 games with the least-used item (were 1 / 18 / 78 / 156);
    5th Loadout when? 3 / 12 / 24 / 35 loadouts (crown 4 %, was 0 %); Pixel Party! 60 / 250 / 500 / 850 deaths (5 %, was 0 %).
  - Gear Veterans (all gear): 15 / 35 / 55 / 80 games (Detonator 7 %, Repair Matrix 5 %, the typical item 2 % over 4 months).
  - Combat all-time, projected from the 3 weeks of reports (x5.8) to a 5 % crown: Ring Debris 120 / 850 / 1,700 / 2,900
    kills, The Whole Echo Crew 140 / 950 / 1,900 / 3,200 assists, Kronos II Salvage 23k / 180k / 350k / 580k damage, Top Bot
    3 / 35 / 70 / 120, Saturn Trifecta 7 / 60 / 120 / 210, Service Android 1 / 17 / 35 / 65, Lone Echo MVP 4 / 40 / 70 / 120,
    Sentinel and Chief Medic 3 / 16 / 27 / 41, Saturn Specialist and Streak Master 2 / 10 / 18 / 28, The Anomaly Doesn't Move
    14 / 140 / 290 / 520 min, Life Support Systems 50 / 390 / 780 / 1,300, Old Arena Habits 5 / 40 / 75 / 140, Ready At Dawn
    9 / 85 / 150 / 250. A projection: re-check once the recorder has a month or two of reports.
- **New special: Full Lobby on Kronos II** (user, 26 Nov): play a full match (4+ minutes) with 5 players on each team for at
  least half of it. Won or not, one crown; in the Specials tab (Activity). 6 % of public matches in the last 4 months were 5v5,
  and 148 of 306 regulars played one. Challenge total 128 -> 129.

## 2026.11.26.23 — 22:04

- **Forbidden Arsenal is a ladder now** (user, 26 Nov: "the same ladder as the normal weapons"): games with your least-used
  experimental weapon (Starburst, Protostar, Quark, Blazar), on No Gun Left Behind's ladder of 1 / 18 / 78 / 156 games. It was
  "use all 4 experimental weapons", once.
- **"Only <item>" challenges harder, all gear together** (user, 26 Nov): 2 / 6 / 8 / 10 games in one day and 3 / 10 / 14 / 18
  in any 7 days (were 1 / 4 / 5 / 7 and 1 / 6 / 9 / 13). Repair Matrix / Detonator crown 13-16 % (was 22-28 %), the typical
  item 4 % (7 %).
- **Combat challenges harder** (user, 26 Nov; review of 66 regulars in the recorder reports of 4-25 Nov, paired ones together):
  - One Day kills 20 / 45 / 65 / 95 and assists 25 / 55 / 80 / 115 (assists stay above kills): crown 12 % / 15 %
    (were 20 % / 27 %).
  - One Day time on the objective 4 / 10 / 16 / 24 min, heal bubbles 12 / 35 / 55 / 80, damage 5k / 14k / 21k / 30k,
    objective eliminations 30 / 75 / 120 / 165: crown 3 % each (were 11-17 %).
  - Most kills in the match and the MVP card in one day: 2 / 4 / 6 / 8 (were 1 / 3 / 4 / 5): crown 2-3 %.
  - Guard and Medic cards in any 7 days: 2 / 3 / 5 / 7 (were 1 / 2 / 3 / 4): crown 5 % / 2 %.
- **"How it counts" written out in full** (user, 26 Nov). Every challenge card lists its rules as sentences ("Your best single
  game counts", "Only games of 4+ minutes count", "Only games with 3+ players on each team count" ...), says "Any game length"
  / "Any team size" where there is no such rule, and ends with "Public matches only, played inside the challenge period".
- **The "Combat and Edit your Bio (separate)" line under the challenge bar is gone** (user, 26 Nov).

## 2026.11.26.22 — 21:50

- **The easiest challenges made harder** (user, 26 Nov, review of every challenge on 194 regulars in the local
  stats-version-20 matches; paired challenges change together):
  - Every gear Veteran (all 22, Overclocked included): 10 / 25 / 40 / 60 games (was 5 / 15 / 25 / 40). Detonator and Repair
    Matrix, the easiest, drop from a 10-12 % crown to 7 %; the typical item 3 % (more over a 3-4 month period).
  - Tech Support w/RAD_Natalie 18 / 21 / 23 / 25 % and Hug Your Frenemy 9 / 11 / 13 / 15 % (were 16 / 19 / 21 / 23 and
    8 / 9.5 / 11 / 13): crown 6 % and 5 % (both 9 % before).
  - Echo Streak 3 / 5 / 7 / 9 wins in a row (was 3 / 5 / 6 / 7): crown 4 % (9 %).
  - My Other Chassis Is a Toaster 3 / 10 / 20 / 30 games (was 2 / 8 / 15 / 23): crown 6 % (9 %).
  - The "only <item>" day and 7-day challenges stay: only Repair Matrix and Detonator are easy (22-28 % crown), the typical
    item is on target at 7 %, and all gear shares one set of numbers.

## 2026.11.26.21 — 21:38

- **Won-or-not challenges have one tier, the crown** (user, 26 Nov: "there is no point having different medals, it is just won
  / not won"). The 16 one-match award cards, Flawless Chassis and Edit your Bio: one pink bar, empty or full, and the card shows
  a single crown step. The "total cards won" ladders keep their four tiers.
- **Lone Echo harder** (user, 26 Nov): 95 / 98 / 99 / 99.5 % of the game away from teammates (was 93 / 97 / 98 / 99). 53 / 24 /
  13 / 9 % of the 219 regulars in the local stats-version-20 matches reach each tier (was 72 / 35 / 24 / 13 %).
- **Emote challenges doubled** (user, 26 Nov: "feasible, people just don't do it regularly"): Lobby Mime Troupe 4 / 12 / 16 /
  20 emotes in a game without dying (was 2 / 6 / 8 / 10; the best regular in the newest local replays did 5, the archive's best
  since 1 August 11), Showbot 8 / 12 / 14 / 16 emotes in a win (was 4 / 6 / 7 / 8; 10 / 4 / 2 / 1 % of regulars, record 18).
- **Space Statue retired** (user, 26 Nov: standing still "seems like throwing"); no other challenge rewards standing still.
  Challenge total 129 -> 128.

## 2026.11.26.20 — 21:14

- **Award cards sorted into the period tabs** (user, 26 Nov: no tab of their own). Each tab has an "Award cards" box with the
  cards of its period: the 16 one-match cards in Specials, Most Valuable Jack in One Day, Jack of the Week / Guard Duty / Medic
  on Call in One Week, the six "total cards won" ladders in Cumulative. Tabs: Specials, One Day, One Week, Cumulative.

## 2026.11.26.19 — 21:08

- **Award cards back in a tab of their own** (user, 26 Nov). Tabs: Specials, One Day, One Week, Cumulative, In-game award cards.
  Specials holds the one-game challenges again (Super Ultra Hyper Turbo, Space Statue, Lone Echo, Contested Point, Showbot,
  Lobby Mime Troupe, Flawless Chassis); the award cards tab is boxed by period (One Match, One Day, Cumulative) as before.
- **"Edit your Bio" is back** in Specials, in its own Profile box (user, 26 Nov). Done once the player's page has a bio; out of
  the totals and ranking like Combat.
- **Super Ultra Hyper Turbo a little harder for regrab speeds** (user, 26 Nov): 19 / 24 / 30 / 37 m/s (was 18 / 23 / 28 / 35).
  Read with the current top-speed code on the 1,538 newest local replays (4+ min 3v3 games), 54 / 10 / 3 / 1 % of the 125
  regulars reach each tier (was 69 / 14 / 4 / 2 %); the fastest is at 37.9 m/s.
- A regrab special ("speed gained with a teammate") was built and then dropped at the user's request the same day: no new
  stat, no extra re-read.

## 2026.11.26.18 — 20:46

- **Challenge bar: complete challenges only** (user, 26 Nov: the tier split was still confusing). One crown-pink bar filled to
  the challenges fully complete, with the share at its end ("30 of 129 challenges fully complete · 23%"). The count per tier,
  the challenges not started and the average progress are in the hover text. The Combat line reads "Combat challenges
  (separate): 1 of 9 complete". The same on the profile row.
- **Super Ultra Hyper Turbo needs full-size games** (user, 26 Nov): like the other one-game challenges, a top speed only counts
  in a game of 4+ minutes with 3+ players per team (it counted any game). Its card lists both rules.

## 2026.11.26.17 — 20:43

- **Centurion Bot and Payload Hauler retired** (user, 26 Nov: "overlap is ok, just avoid duplicates"). Their counts were made
  entirely of other challenges (all wins = Capture Point + Payload wins; Payload wins = attacking + defending wins). Challenge
  total 131 -> 129.
- **Challenge cards say how they count** (user, 26 Nov). The pop-out card lists the counting rules under "How it counts"
  instead of one grey line. Super Ultra Hyper Turbo now spells out its rules: best game; top speed = your fastest average speed
  over 1 second; regrab flights and shooting backwards count; instant launches, readings over 100 m/s and jumps in the
  recorder's clock do not; any game length and team size.
- **Mega Prizes on a player's Challenges page** (user, 26 Nov): the same one-row personal progress as on the profile, under the
  tier bar (only for who may see the Mega Prizes).

## 2026.11.26.16 — 20:14

- **Specials is the first tab** (user, 26 Nov); the Challenges page opens on it. Tabs: Specials, One Day, One Week, Cumulative.
- **Award card boxes stay together** (user, 26 Nov): in Specials an award card box only sits beside another award card box,
  and a topic box only beside another topic box.

## 2026.11.26.15 — 20:11

- **Five more one-game challenges retired** (user, 26 Nov: the closest overlaps left): Untouchable Chassis (Flawless
  Chassis, My Other Chassis Is a Toaster), Ghost of Sparta (games with more kills than deaths), Ambidextrous Bot (Two-Handed
  Bot), Point Guard (time on the objective) and Siege Breaker Bot (the Point Control award card). Challenge total 134 -> 131.
- **"Edit your Bio" removed** (user, 26 Nov).
- **One tab less: "In-game award cards" is now "Specials"** (user, 26 Nov). The one-game tab is gone; its challenges moved into
  Specials: Super Ultra Hyper Turbo (the single-game speed challenge), Space Statue, Lone Echo, Contested Point, Showbot, Lobby
  Mime Troupe and Flawless Chassis, in their topic boxes, then the award cards in boxes by period ("Award cards · One Match",
  "· One Day", "· Cumulative"). Tabs: One Day, One Week, Cumulative, Specials; the page opens on One Day.

## 2026.11.26.14 — 19:55

- **Super Ultra Hyper Turbo is much harder** (user, 26 Nov): 18 / 23 / 28 / 35 m/s top speed (was 14 / 20 / 23 / 28). Of the
  348 regulars in the newest 4,000 public matches, 51 / 12 / 3 / 1 % already reach each tier (was 84 / 32 / 12 / 3 %); the
  fastest is at 38.5 m/s, so the crown stays reachable.
- **Beam Me Up, Translocator retired** (user, 26 Nov). Specials is down to 13; challenge total 135 -> 134.
- **No empty space in the challenge boxes** (user, 26 Nov). On every tab, a short box now sits beside another short box only
  when both have the same number of challenges (same height); a short box without such a partner takes the full width. In a
  full-width box with an odd number of challenges, the last one stretches across both columns instead of leaving a gap.

## 2026.11.26.13 — 19:36

- **Regrab top speeds no longer cut in half** (user, 26 Nov: "they said 48 m/s"). In regrab flights the game reports a
  velocity of exactly 0 for runs of 5-10 frames while the player flies on at 40-68 m/s (12 % of moving frames in these
  matches). Top speed takes the lower of the readings and the distance covered, so those zeros halved it. Such a frame now
  counts at the head's speed since the frame before; every other check stays (launches, impossible readings, gaps, clock
  steps). DinkatorBoi 28.9 → 47.3 and JavaBava 26.4 → 45.5 (match 312237), 30.9 → 49.3 and 29.1 → 48.2 (match 315101).
  Average speed still uses the readings as they are.
- In the 1,555 newest local replays 226 of 9,441 player-matches go up (median +2.5 m/s), 1 goes down 0.7. Players reaching
  the speed challenge's 23 m/s: +2 of 882 (14: +5, 17: +9, 20: +10); the targets stay. Fastest player-matches, counted or
  not: DinkatorBoi 49.3, JavaBava 48.2, DinkatorBoi 47.3, JavaBava 45.5, DinkatorBoi 37.9 (their 2026-11-02 regrab,
  unchanged). (Corrected 2026.11.27.4: the four fastest are 0 v 2 / 1 v 2 practice games, which do not count, so the
  home-page top 5 keeps DinkatorBoi 37.9 and JavaBava 37.7.)
- **After the update** every replay is read again (stats version 21, hours on the NAS); it replaces the version 20 re-read.
  Until it is done, old and new top speeds are mixed in the lists and challenges.

## 2026.11.26.12 — 19:27

- **"Fully complete" made obvious** (user, 26 Nov). The challenge bar's headline now reads "30 of 135 challenges fully complete
  · every tier, up to the crown", with the pink crown beside it and the number in crown pink; on the profile row "31 of 135
  fully complete".
- **Top players: ranked by challenges fully complete** (user, 26 Nov). The challenges page's Top players now lists the players
  with the most challenges fully complete first (average progress only breaks a tie), each as "crown 36 / 135 fully complete".
  The Challenges leaderboard (stats page) still ranks by average progress.

## 2026.11.26.11 — 19:20

- **Specials trimmed to 14** (user, 26 Nov, D64). Retired, because One Day / One Week / Cumulative (or another Special)
  already covers them: Full Team Salvo, Can We Talk About This?, I'm Bat Bot, Jack of All Trades, Ordnance Sampler, Tac Mod
  Tinkerer, Kronos II Armory Raid, Bomb Bay Overload, Payload Pedal to the Metal, Payload Roadblock, Marathon Bot, Boost
  Junkie, Quick-Change Chassis, and the Combat Chassis Crusher, Wingbot, Hull Breach, Net Positive Bot, Point Denied, Parked on
  the Point, Repair Matrix Medic, Stun Field Trooper and Jack's Toolkit. They are gone from the site, totals, ranking and
  Medal Collector. Left: Super Ultra Hyper Turbo, Space Statue, Lone Echo, Ambidextrous Bot, Point Guard, Contested Point,
  Showbot, Lobby Mime Troupe, Untouchable Chassis, Beam Me Up, Flawless Chassis, Ghost of Sparta, Siege Breaker Bot and Edit
  your Bio. Challenge total 148 -> 135.
- **Challenge bars: one segment per tier** (user, 26 Nov). Each row's bar is now four separate pieces with a clear gap, each
  in its own colour (bronze, silver, gold, pink crown); the empty part of a piece is a faint wash of its colour, so every tier
  shows before it is reached.

## 2026.11.26.10 — 19:03

- **Player profile: Challenges and Mega Prizes are one row each** (user, 26 Nov: "too much data"). Challenges: the label,
  "38 of 148 complete", the tier bar with its names inside and a "View all →" button on one line; the counts of the small
  segments, average progress and the Combat / Edit your Bio line moved into hover text. Mega Prizes: "Delta-13" and "Jack
  Series 11", each with a slim bar and "412 / 1,000" (or "won!"); the full prize name, the rule, how many to go and the period
  are in hover text, and a green dot shows while matches are being recorded. On a phone the rows wrap and the bar shows numbers
  only. The challenges page keeps the full-size bar.

## 2026.11.26.9 — 18:56

- **"Medal" is now "tier" everywhere on the site** (user, 26 Nov: "medals" was confusing next to the crown pictures and the
  Crown tier). "No tier yet" in the bar, "Recent tiers reached", "Closest to next tier", "x% of players reached a tier",
  "Tiers and progress" on the profile tab, "tiers reached in total" in Top players, and Lobby Mime Troupe's rule. The
  "Medal Collector" challenge keeps its name.
- **"Your next tiers · closest first" is back, with more detail** (user, 26 Nov). Five cards above the tabs on a player's
  Challenges page, closest first. Each shows the challenge and what to do, "3 more to reach silver" in the colour of that tier,
  a bar to it with the count ("24 / 27 · 84% of the way"), the four tier crowns (reached, next, later) and how many players
  have reached a tier in it.

## 2026.11.26.8 — 18:48

- **Challenges: a simpler medal bar** (user, 26 Nov, option B). The bar on the player profile and at the top of their
  Challenges page now has one headline, "30 of 148 complete", and each coloured segment says what it is: Crown 30, Gold 17,
  Silver 16, Bronze 24, No medal yet 61. Segments too narrow for their name are named just under the bar; on a phone the bar
  shows the numbers and a coloured key underneath names them all. "Average progress" moved into the headline's tooltip, and
  the unlabelled dots are gone. Combat and Edit your Bio, which are not in the totals, get their own small line.

## 2026.11.26.7 — 18:23

- **Challenges: "One Match" is now "Specials"** (user, 26 Nov, D63). The tab keeps only the one-of-a-kind single-match
  challenges (36): loadout stunts, movement, Payload, Capture Point, emotes, Untouchable Chassis, Marathon Bot, Beam Me Up,
  the four original one-match challenges, the Combat feats and the new "Edit your Bio". The award cards tab keeps its
  "One Match" heading.
- **The 22 Test Drives are retired** ("Use <item> for 3 minutes in one game"). They are gone from the site, the totals, the
  ranking and Medal Collector; the Veteran and "only <item>" challenges cover the same gear. Challenge total 170 -> 148.
  Average progress and rankings shift a little after the update; the challenge period has no start date yet, so no earned
  medal is lost.
- **New special: "Edit your Bio"**. Done once the player's page has a bio (log in with Discord, then edit it on the profile).
  Like the Combat challenges it is out of the totals and ranking. Its icon can be chosen in Console > Achievements.

## 2026.11.26.6 — 17:52

- **Challenges: topic boxes, crowns and notches** (user, 26 Nov). Each tab now groups its challenges into boxes by topic
  (Weapons, Ordnances, Tac mods, Loadouts, Payload, Capture Point, Maps, Movement, Positioning, Survival, Emotes, Wins,
  Activity, Combat), each with its own progress; short topics sit side by side. The award cards tab is boxed by period. Icons
  are white until you point at a row, then take the colour of the medal reached. Every bar has a notch at each medal step.
  The card shows each step's medal crown in its own colour, ticked once reached, and the crown of the medal reached on the
  big picture (the pink lock before the first medal).
- **Challenges page: "Your next medals" removed** (user, 26 Nov). "Not yet started" stays.
- **Player profile: Mega Prizes** (user, 26 Nov). A Mega Prizes section under the challenge strip shows only that player's
  own progress toward each prize (Delta-13: Combat matches, Jack Series 11: Public Arena matches), with a bar, the count and
  how many to go, or "prize won!". No ranking and no other players. Shown to the same people who see the Mega Prizes now
  (Console "Visible to"). Counts come from every game account linked to the player. New Preview-only endpoint
  `/api/arena/player/{id}` (sends no Discord or game account ids back).
- **Player profile: no more "Your goals"** (user, 26 Nov). The challenge strip keeps the big medal bar, with a large
  "View all <name>'s challenges" button under it.

## 2026.11.26.5 — 17:19

- **Challenges: the classic list is back, modernised** (user, 26 Nov: the original ECRanked layout is easier in VR). Each tab
  is now two columns of rows: the icon on the outer edge, the name, and a slim bar in the colour of the medal reached
  ("Completed!" when every medal is done). Pointing at a row (mouse or VR controller) shows a card with the big picture and
  every medal step ticked off, with its target and how far along the next one is. A click or tap pins the card open; another
  click, the cross or Esc closes it. The period tabs are big coloured buttons (One Match cyan, One Day coral, One Week
  green, Cumulative violet, award cards orange), each filled to the player's progress in it. Search, status and sort sit
  behind the funnel button beside the tabs, so nobody has to type. The list keeps the original order by default ("Closest to
  next medal" is in the sort menu), and completed challenges show with the rest rather than behind a Completed filter. Phones
  get a single column. Nothing to do: shows after the update.

## 2026.11.26.4 — 17:10

- **Matches per map: every weapon, ordnance and tac mod** (user, 26 Nov). The Weapon / Ordnance / Tac mod chips now list all
  gear that was ever held, not only gear held 0.5 % of the time or more. New: Blazar (0.09 % of weapon time), Dot Field
  (0.11 %), Attack Drone (0.01 %), Overcharge, Umbral Veil and Neutron (each under 0.01 % of tac mod time). Gear that rare has
  too little for "Favoured spots" on most maps, so the note under the cards says so and offers "Show everywhere it was held",
  which draws it on every map. The heat still counts where gear is carried: the replays do not say when it is fired or used.
  No re-read; the new chips show after the update.

## 2026.11.26.3 — 17:06

- **New Challenges tab: In-game award cards** (user, 26 Nov). The 25 challenges for the game's end-of-match award cards (MVP,
  Super Star, Guard, Medic, Assassin ...) moved out of One Match / One Day / One Week / Cumulative into one tab, split inside it
  under those same four headings (16 / 1 / 3 / 5). The status pills, search and sort work there as on the other tabs, and a
  player's summary has a tile for it. Links to `?section=p-awards` open it. Frontend only, nothing to re-read.

## 2026.11.26.2 — 14:59

- **An instant solo launch gives no top speed** (user, 26 Nov: "big spikes as a solo are not realistic, as shooting behind you
  is a gradual growth"). A player under 10 m/s who gains 20+ m/s within a twentieth of a second, with nobody moving at 5+ m/s within
  2.5 m, is launched: no second holding the launch or the coast after it counts, until they slow under 10 m/s. Bree_Plays
  (Combustion 2022-05-11) went from 0.4 to 60 m/s in one frame along the floor and stopped dead: 41.6 → 13.9. Also e_g2012
  35.7 → 10.6, P.R.E.C.L.O.U.D 35.2 → 13.3, MUSTYVR 33.6 → 9.9, Vibinator 33.0 → 8.3, oculususername1229 31.9 → 10.9.
- **Regrabs and gradual speed-ups still count** (user): DinkatorBoi / JavaBava 37.9 / 35.6 (flinging each other, 0-2 m apart),
  Caprison- 42.1 and Chroined 39.9 (out of Dyson's tubes, 1 → 51 m/s over 2 s, shooting behind them). A sudden stop is a wall crash
  and is fine.
- **A step back in the recorder's clock starts a new top-speed window** (user: "make sure you are handling clock jumps, or time
  skips"). Nektwo 55.1 → 14.2 and davidyarker 52.5 → 14.3 (Combustion 2022-01-09, the clock went 4.8 s back: 4.8 s of flying was
  counted as one second); Schmoculus 38.0 → under 18 the same way.
- Of 220 player-matches at 20+ m/s in the 1,551 newest local replays 26 change; 179 of 180 regrabs keep their speed (dr4coo
  21.2 → 20.2). New home-page top 5: Caprison- 42.1, Chroined 39.9, DinkatorBoi 37.9, JavaBava 35.6, Rapollo2126 34.6.
- **After the update** every replay is read again (stats version 20, hours on the NAS); it takes the place of the re-read for
  version 19. Until it is done, speeds by the old and the new rule are mixed in the lists and challenges.

## 2026.11.26.1 — 09:42

- **A speed reading over 100 m/s is impossible** (user, 26 Nov): a second that holds one gives no top speed. These are the game
  throwing a player out of the map's geometry: Hezza_ (Dyson, 20 Nov 01:33, #4 on the home page at 34.1 m/s) went from 2 to 121 m/s
  in one frame and back. Real flights stay under 60 m/s. Of 24,694 player-matches in the newest 1,680 matches 39 change: Derkit1304
  31.1 → 10.6, Hezza_ 34.1 → 27.4, Scoob 36.7 → 33.4; the fastest real flights (Caprison- 42.1, Chroined 39.9, DinkatorBoi 37.9)
  stay the same.
- **After the update** every replay is read again (stats version 19, hours on the NAS); it takes the place of the re-read for
  version 18.

## 2026.11.25.5 — 21:48

- **Top speed is the fastest average over one second, and the distance has to be travelled** (user, 25 Nov: no peaks, "this can easily
  be cheated"). Before, it was the slowest moment of the best second. Turns and straight flight both count; where the player aims
  and what they grab does not matter. One reading cannot set it, and standing frozen or shaking on the spot is no distance.
- Top speeds read about 10 % higher (median of 8,089 in the newest 1,600 matches); every other stat is the same.
- **Super Ultra Hyper Turbo** is 14 / 20 / 23 / 28 m/s (was 13 / 17 / 19 / 21), which is as hard as before under the new rule:
  100 / 54 / 22 / 11 % of the 90 regulars reach it, before 99 / 49 / 21 / 10 %.
- **After the update** every replay is read again (stats version 18, hours on the NAS); it takes the place of the re-read for version
  17. Until it is done, speeds by the old and the new rule are mixed in the lists and challenges.

## 2026.11.25.4 — 21:05

- **Super Ultra Hyper Turbo is slightly easier on every medal** (user, 25 Nov): top speed in one game 13 / 17 / 19 / 21 m/s for
  bronze / silver / gold / crown (was 14 / 18 / 20 / 22). Of the 90 regulars (25+ games in the newest 1,600 matches, with the
  corrected speeds) 99 / 50 / 21 / 10 % reach them, before 88 / 34 / 13 / 7 %.
- Needs the update deployed (restart); nothing is re-read, medals are worked out from the saved speeds.

## 2026.11.25.3 — 20:46

- **Home: "Top 5 fastest players"** instead of the one fastest player (user, 25 Nov): name, speed, and the map, date and time it
  was reached, with a link to that match. Each player once, with their best match; counted games only (2+ minutes, 2+ players per
  team), so it agrees with the leaderboard and Records.
- **Player page: the top speed opens the match it was reached in**, with its map, date and time under it. It follows the period
  and map picked on the page.
- API: `/api/overview` `global.fastest` is now `global.fastest_players`; `/api/players/{id}` `stats.top_speed_match` is new.
- Needs the update deployed (restart); nothing more is re-read. Until the re-read of 2026.11.25.2 has reached the old
  glitched matches they stay in the list.

## 2026.11.25.2 — 20:31

Top speed is real movement only (user, 25 Nov: "the most accurate speed"):
- **The three fastest records were glitches:** a player whose data stops coming (lag, loading into the match) stands still
  but keeps the last speed. Schmoculus 51.77 m/s (frozen 10.7 s, moved 0 m), SupaStav 45.91 (moved 0.75 m) and
  ErrorNameNotFound 38.50 (frozen 66 s) are now 8.96, 11.15 and 9.60 in those matches. The fastest player is Caprison-, 35.28 m/s.
- **Top speed** still is the fastest speed held for a full second, but that second only counts when the player ended up
  where the speed takes them (within half of the distance), and not across a gap in the recording of more than 0.5 s.
- **Average speed and distance:** a player frozen for 0.5 s or longer adds nothing. Time in bounds, time stopped, deaths and
  everything else are unchanged.
- Measured on the 200 newest replays of each map (4,272 player rows): 55 top speeds are lower, none higher, none lost a
  challenge medal; distance falls by 0.02 % in total. Everybody else in the top 10 keeps their number.
- The calculation itself was already in 2026.11.25.1 (its note says that nothing is re-read: it is, stats version 17).
- **After the update** every replay is read again (hours on the NAS): the old records stay until their match has been.

## 2026.11.25.1 — 20:23

Link and unlink Discord accounts on the Console (user, 25 Nov: "in case they are wrong or broken"):
- **Console > Players > Player tools** shows each player's Discord account, how it was linked (bot or admin, the player
  id is the Discord id, seen on the match list, same name) and **Unlink** / **Link an account…** buttons. The search also
  takes a Discord id. The same as forms: "Link a Discord account", "Unlink a Discord account" and "Discord link report"
  (the commands existed but had no button). Everyone with Console access can use them; each use is in the audit log.
- **An unlink now holds.** Before, it only removed the bot's / admin's link, so the site found the same account again by
  player id, match list or name. The two now stay apart everywhere (bio, picture, edit rights, "Linked account", the Mega
  Prize replay history) until somebody links them by hand ("Link again").
- **A link by hand overrules the automatic ones:** that account shows on no other player, and the player has no other
  account. Before, an account could show on two players at once.
- The bio and the "show my picture" choice move with the Discord account instead of being lost.
- A link made before a player was merged now works on the main player and can be removed there.
- **Bot:** `/api/bot/link` answers 409 `link_blocked` for a pair unlinked on the Console. Links and unlinks by the bot
  work as before otherwise, and its own unlink blocks nothing.
- admin.bat: menu option 22, `unlink-profile <player> [<discord id>]`.
- Needs the update deployed (restart); nothing is re-read. The new table `discord_link_blocks` is made at the start.

## 2026.11.20.5 — 10:32

One row per weapon in the Combat lists (user, 20 Nov: "Nova and Nova Cone? those are the same weapon"):
- **Kills / Deaths / Shots by weapon** on a player's Combat tab and on a match no longer split a weapon into parts:
  Nova cone is added to Nova, Meteor splash (was "Meteor blast") to Meteor, and Comet splash (was "Comet blast") to
  Comet. The two spellings the recorder uses for an ordnance (`det` / `r15_ord_det`) are one Detonator row too, and the
  two blank-weapon marks are one "Unknown weapon" row.
- Nothing to do: the merge happens when the page is shown, so old and new matches show it at once. No re-read.

## 2026.11.20.4 — 05:29

Achievements are now called **Challenges** everywhere on the site (user, 20 Nov):
- **New address:** the page is `/challenges` (a player's: `/challenges/<name>/<id>`), and the menu, page titles, the
  player profile tab and strip, the Leaderboard stat ("Challenges (overall %)"), the Console (Challenges tab, "Export
  challenges", launch-date texts, Status card) and the Permissions page say Challenges. The CSV export is
  `EchoVR-Challenges.csv`. Phrases like "achievements and challenges" became just "challenges".
- **No broken links:** `/achievements`, `/achievements/<id>`, `/achievements/<name>/<id>`, `/achievements?player=<id>`,
  `/challenge` and `/mega-prizes` move to the new address, keeping the player, query and anchor. `?stat=achievements` on
  the Leaderboard, `?tab=achievements` on a profile and `?tab=achievements&cmd=export-achievements` on the Console still
  open the same board / tab (the site's own links now use `challenges`). The Discord login now returns to `/challenges`.
  Checked in a browser against the built site with the site's own page server.
- Unchanged on purpose (not shown to people): the API addresses (`/api/achievements`, ...), the badge art folder
  (`/achievements/<icon>.png`, so saved icons and uploads keep working), code and file names, and settings keys.
- Needs the update deployed (restart); nothing is re-read.

## 2026.11.20.3 — 05:07

New gear challenges and icons (user, 20 Nov):
- **Attack Drone, Umbral Veil and Neutron** get the same four challenges as every other new item, on the same targets:
  a Veteran ladder (games using it), "only X" in one day, "only X" in any 7 days, and a 3-minute Test Drive under "In one
  game". 12 new challenges, ids 265-276 (no existing id moved): Attack Drone Veteran / Attack Drone Ace / Attack Drone
  Swarm (Ordnance), Umbral Veil Veteran / Behind the Umbral Veil / Shrouded in the Umbral Veil (Tac Mod), Neutron
  Veteran / Neutron Star / Neutron Flux (Tac Mod), and the three Test Drives. They count in totals like the rest, so the
  challenge total goes from 158 to 170. The 240 released loadouts (loadout challenges) stay as they were.
- **New icons** from the user's art, tinted by the medal like the other gear: Dot Field (Dot Field Veteran, Dot to Dot,
  Dot Matrix, the Dot Field Test Drive), Overcharge (Overclocked, Full Charge, Charged Up, the Overcharge Test Drive),
  Attack Drone, Umbral Veil and Neutron (their new challenges). Beam Me Up, Translocator keeps the Translocator icon.
- The source art (1024 px) is kept in `images/`: blazar, buff (Overcharge), dot, drone, medigun, point (Neutron),
  protostar, quark, smoke (Umbral Veil), starburst, translocator.
- Needs the update deployed (restart); nothing is re-read. An icon an admin picked on the Console page still wins.

## 2026.11.20.2 — 04:34

Achievement icons (user, 20 Nov):
- **Speed challenges** (Super Ultra Hyper Turbo, The Wings of RAD_Wyvern, Cyberkinetic Enhancements, Boost Junkie) use
  the new LAUNCH icon, tinted by the medal like the rest. The blue and orange originals are the same shape, so one file
  covers both.
- **Grind challenges** (Marathon Bot, Overtime on Kronos II, Time Well Wasted on Kronos II, Combat on Quest When?) use
  the sweaty robot. It keeps its own colours: as a one-colour silhouette it is an unreadable blob. Built-in icons named
  `colour_…` now show in their own colours, like uploads (no daily / weekly variants for them).
- **Healing +** on Repair Matrix Medic, Medic on Call and Field Medic; **Stun Field** on Stun Field Trooper and Kronos
  II Shock Trooper (all Combat).
- **Gear reticles:** sharper Blazar, Protostar, Quark and Translocator icons from the new full-size art; an Umbral
  Veil icon is in the icon picker, unused until Umbral Veil has a challenge.
- Admin icon choices made on the Console still win over these defaults.

Recorder stats: "Shots by weapon" showed **"?"** (for example 1,040 shots on one profile). That is the recorder's mark
for a shot whose nearest replay frame named no weapon (the replay leaves the field empty in up to 37 % of player-frames):
15 % of all recorded shots, up to 68 % of one player's. It now reads **"Unknown weapon"**, with a note in the tip.

Damage taken in one life: not buildable. The recorder's `damage_taken` is always 0 (the game does not send it to
spectators), the event log has no hit events, and replays hold no health.

## 2026.11.20.1 — 03:49

The site was very slow (user, 20 Nov). Measured on the live site (version 2026.11.19.1, up 4.3 h, no replays waiting):
around 03:26 UTC a match list took 36 s and the home page's numbers (`/api/overview`) more than 30 s, so the page gave up
and stayed on its grey boxes; even the login answer took 0.7 s instead of 0.1-0.2 s. Ten minutes later every answer took
0.05-0.25 s (0.3-1.6 s for one nobody had asked for yet), and a 5-minute probe stayed at 0.05 s. The busy spell itself is
not explained yet (the NAS log of 03:15-03:40 UTC will say). What it showed: Cloudflare kept answering everything it
keeps, but the **home page's numbers, the leaderboard and every player profile were never kept by Cloudflare**
(`cf-cache-status: BYPASS`): while stats are hidden from players, those answers asked who the visitor is (admins see
the hidden stats), so every visit went to the NAS. Asked for: keep more on Cloudflare to take load off the NAS (user).

- **Cloudflare keeps the home page, leaderboard and profiles again** (`/api/overview`, `/api/leaderboard`,
  `/api/leaderboard/overview`, `/api/leaderboard/stats`, `/api/players/<id>` with trends, companions and compare):
  asked for plainly they are always the public version (hidden stats left out) and nobody is asked who they are, so
  they are the same for everyone. Before: every visit built or read them on the NAS (0.05-0.15 s when warm, 1-1.6 s the
  first time, more than 30 s in the busy spell); now repeats come from Cloudflare (0.02-0.03 s measured on the answers it
  already kept) and, as before, Cloudflare serves the last good copy for up to 10 minutes if the NAS fails. They also
  join the list of answers rebuilt after a restart (they were left out as per-visitor).
- **Admins still see hidden stats**, on their own copy: `/api/auth/me` sets an `echovr_admin` cookie for admins (a hint
  only; it is removed on logout or when the admin role goes), and the page then asks for those answers with
  `view=admin`. Only then is the login checked; that answer is `private, no-store` and never kept by Cloudflare. A
  non-admin who adds `view=admin` still gets the public stats; an admin who asks without it gets the public copy, so
  what Cloudflare keeps is never an admin's.
- **The challenge period (`/api/challenges`, asked on every page) is kept by Cloudflare too**: it carries `previews`
  (the preview role sees achievements before the launch) instead of whether this visitor has the role; the page takes
  that from `/api/auth/me`, which it asks anyway. Before the launch the leaderboard's achievements stat is listed with
  `"preview": true` and shown only to previewers.
- **Cloudflare keeps public answers 5 minutes instead of 1** (`ECHOVR_EDGE_CACHE_S` 60 -> 300; user: 10 minutes behind
  is fine). With the server's own 5-minute refresh and the tab's 1 minute, a new match shows within ~1-6 minutes,
  at most ~11. Live status and the processing count are never kept (unchanged). An admin change (hide stats, merge,
  challenge period) can take up to 5 minutes to reach Cloudflare's copies (was 1).
- `check_cloudflare.bat` also checks that the home page's numbers come from Cloudflare and that an admin's copy never
  does. Setup.MD: new step 4b, Smart Tiered Cache (free: Cloudflare's data centres ask one upper tier instead of each
  asking the NAS).

**To do after updating:** in the NAS's YAML set `ECHOVR_EDGE_CACHE_S: "300"` (or remove the line: 300 is the default
now), Recreate, then run `check_cloudflare.bat`. In Cloudflare: Caching > Tiered Cache > Smart Tiered Caching on.
Admins: open any page once after the update (sets the cookie), then reload to see hidden stats.

## 2026.11.19.1 — 23:07

Replays with bone data (recorder update, 19 Nov) failed to import: every one ended "Too many unreadable lines". Each
frame line is now `<time>\t<frame>\t<bones>` (the first line has no bones); the frame itself is unchanged.

- **Bone-data replays import again.** The reader takes the frame and skips the bones part (nothing on the site uses
  bones yet). Checked on 6 replays from the share (5 with bones, all four maps, up to 15.5 min): every frame read, no
  warnings; players, kills and deaths match the raw frames; 2D and 3D tracks written.
- **Size limit for one replay 1 GB -> 2 GB uncompressed** (the zip-bomb guard): bones add ~40 % to a replay (a 15.5-min
  Dyson match is 364 MB), so a ~45-min match would have hit the old limit.
- **The ones that already failed are re-read once at startup**: failed, file from 19 Nov or later, with the old error.
  Nothing else is re-read (`PARSER_VERSION` stays 3). The error for a really damaged replay now reads "Too many
  unreadable frame lines", so these rows never re-queue twice.
- `tools/maps3d/sample_heads.py` reads bone-data replays too.
- **To do:** deploy to the NAS, and `git pull` on the remote-processing PC too: with the parser version unchanged, a PC
  on the old code is still accepted and would fail these replays.

## 2026.11.18.1 — 13:51

The site stuck at "Processing 13 replays" (user, 18 Nov; the same as "Processing 50" on 16 Nov). From a copy of the live
database: healthy this time (quick check ok, indexes agree with the table), remote processing off, 13 replays queued
and none processing, the last one saved at 00:50 UTC, while combat reports and everything else kept being written until
13:39. So the NAS's replay worker had stopped between 00:50 and 01:00 UTC and never started again. The exact error is in
the NAS log ("Worker loop stopped").

- **The replay worker no longer stops for good after an error.** Any error while claiming, saving or restarting the
  pool used to end the worker until the container was restarted (on 16 Nov a damaged index; today unknown). Now it is
  logged as `Replay worker error (N in a row); trying again in N s`. Replays it had picked up but not started, or whose
  save failed, go back into the queue. With nothing in flight the reader processes are started afresh, and it tries
  again after 2, 4, 8 … up to 60 s.
- **Console > Status, Speed card:** shows the worker's last error (it retried by itself), or "The replay worker has
  stopped: restart the container" if the thread is gone. `/api/import` adds `worker_running` and `worker_error`.
- Not covered: a replay that hangs while being read (it stays "processing", with its time growing on the Status page).

**To do after updating:** nothing. Updating restarts the container, and the 13 waiting replays are read then.

## 2026.11.16.22 — 16:00

The first load of pages nobody has opened since the last restart (user: "stuff that isn't cached, a brand new load
in"). Measured on the live site first (version 2026.11.16.20): minutes after a restart a match-list filter took 21 s,
the most active player's profile 13.5 s, the Records board 2.4 s, a match 1 s; the same kinds of request took
0.1 - 0.3 s ten minutes later. The site restarts with every update, so that window is where first loads are slow.
Only changes worth more than 10 % were kept (user).

- **After a restart the server builds again what people were opening**, most asked first (`popular.py`). It remembers
  which public answers are asked for (`<data>/cache/popular.json`, counts fade over days) and, once the database is
  back in memory, asks itself for the 150 most asked (`ECHOVR_WARM_ANSWERS`, `0` = off), one at a time at no more than
  half a core. Built by the new version's own code: nothing from before the restart is sent to anyone. On the dev PC
  with a realistic list of 150 answers (profiles, matches, boards): their first requests after a restart took 2.25 s
  together (the slowest 357 ms) and now 0.06 s (the slowest 0.7 ms), for 5.5 s of work in the background.
- **The ahead-of-time builds wait for the database to be read into memory** instead of competing with that read for
  the disk.
- **Player profiles: gear picks through a new index** (`ix_events_loadout_player`, gear-change events by player, ~8 MB).
  They were found by reading every event of every match the player was in (1.3 million rows for the most active
  player). First build of that profile 305 ms -> 144 ms on the dev PC, an ordinary one 16 -> 9 ms; much more when the
  rows have to come from the disk. **The first start after this update builds the index once** (0.8 s on the dev PC,
  expect well under a minute on the NAS).
- **Home page numbers**: four separate passes over every player of every match became one (overview build 387 ->
  311 ms; it is built in the background, so this is server time, not waiting time).
- **The page itself and its scripts / styles are sent from memory**, compressed once: a page address 2.6 -> 0.2 ms, the
  main script 7.4 -> 0.2 ms per request on the dev PC (it was compressed again for every request), and 4 % smaller.
- **For reading the log when the site felt slow**: one line at start with the SQLite version and the database size,
  `Slow answer: <name> <filters> took N s to build` for every build over 2 s, and how many answers were built again
  after the restart.
- Looked at and left alone (under 10 %, or nothing cheaper found): replay processing (a set of per-frame savings
  measured at under 2 %, taken out again), the leaderboard's one pass over the archive, the Records board, heatmaps.

**To do after updating:** add `ECHOVR_WARM_ANSWERS: "150"` to the NAS YAML only if you want a different number (150 is
the default). The first start takes a little longer once (the new index).

## 2026.11.16.21 — 15:23

Home page, from the user's screenshots on a 2500 px window.

- **No trend line on three cards**: "Matches · last 7 days", "New players · last 7 days" and "New players who came back"
  no longer say "… vs the 7 days before"; the number, the small line and "0 today" / "77 of 215" stay.
- **"All time" cards lined up**: the cards of a row are one height across Archive / Fun facts / Records (they were
  107 / 103 / 142 px) and one width, and every row ends at the right edge. A very wide window gets two full rows
  (Archive + Fun facts, Records + More archive numbers) instead of 15 cards and two stretched ones left over below.
- **"This week" fills its panel**: it shows as many ranked players as it has room for (five at least, up to 15) instead
  of five and an empty panel beside the video; the Combat tabs add kills per death / award cards next to the matches.
  The overview now carries the 15 most active players of the week (was 5).
- **"Players seen in Combat" is smaller**: title, total and period on one line, no chart heading, and a short chart
  (139 px for the whole panel on a wide window, was about 240; beside "This week" it fills that panel's height). The
  "From the latest match" tick box is gone: when nobody played in the period counted back from now, it counts back
  from the newest match by itself and says so.
- The chart's data is asked for early with the range it opens on (7 days; it asked for 24 hours, which was thrown away).

## 2026.11.16.20 — 14:47

End-to-end pass for load times and layout. Measured on the development PC against a copy of the full archive, old and
new code side by side, with a browser on a simulated 10 Mbit / 40 ms connection (17 pages, first visit with an empty
browser cache): **a page is complete after 0.67 s on average, was 0.95 s; the main content shows after 0.52 s, was
0.83 s; a first visit downloads 230-540 KB, was 430-1,460 KB.** The NAS is 5-12x slower than this PC for the server's
part, so the server-side gains are larger there.

**Quicker pages**
- **Pictures are 4-9x smaller.** The background behind the top bar (on every page) is 41 KB, was 275 KB; the map
  pictures under heatmaps and playback are 100-250 KB, were 0.5-2.3 MB; the thumbnails ~20 KB, were ~100 KB (WebP,
  same size in pixels; the PNG / JPG files stay for links that still point at them). Heatmap / Playback tabs: 0.8 s,
  were 1.6 s.
- **The font comes from the site itself**, not from two Google servers (one request less before text settles, and no
  visitor address goes to Google). The Content-Security-Policy no longer allows Google's font servers.
- **Data is asked for while the page's code is still downloading** (`early.js`): the answers every page needs (login,
  achievements state, version, import queue) and the first answers of Home, Matches, a match, a player and the
  Leaderboard are already there when the page starts. The opened page's own code is fetched at the same moment.
- **No loading skeleton on a first visit, and none on the first click on Matches / Leaderboard / Achievements / a
  player / a match.** React holds a page back until 0.3 s after its skeleton appeared, however quickly the page file
  arrives; the opened page's file is now loaded before the first render, and the main pages' files are fetched in the
  background once the browser is idle (not on a "save data" connection).
- **The first download is 10 % smaller** (88 KB, was 98 KB): the top bar no longer pulls in the whole achievements view.
- **Home asked for the Twitch live status twice** every time; once now.

**Server: more kept in memory**
- **Combat stats answers are kept** like the replay ones (leaderboard, player, match list, match, summary): 1 ms, were
  10-30 ms each on every request, and browsers / Cloudflare get an ETag (304 when unchanged). They follow new match
  reports and player merges; like every other page they can be up to 5 minutes behind.
- **Achievements list** (`/api/achievements`): 7 ms, was 130-140 ms per request (the rarity of every challenge was
  counted again for every visitor; now once per ranking). A player's achievements: 5 ms, was 15 ms.
- **After a restart the Matches and Leaderboard first screens are built ahead** (with the match thumbnails), as the
  Home page already was: their first visitor no longer waits for the archive-wide build (leaderboard 2.5 s, match
  list + summary ~1 s on the NAS). 1.4 s of background work at start on this PC.
- **Memory for kept answers is a setting**: `ECHOVR_RESPONSE_CACHE_MB` (1024, and 4096 in the NAS YAML, as much as the disk copy holds: user, "more the better", the NAS has 32 GB; it was fixed at 64 MB = about 400 player
  heatmaps) and up to 20,000 answers (was 4,096). Added to `docker-compose.yml`.
- A Discord picture lookup that fails is not repeated for 30 s (a profile waited 0.6 s for it on every view).
- WebP / WOFF2 files are sent with their proper type.

**Layout**
- Player page, "Your goals" and "Your next medals": the hint under each tile starts on the same line, whether the
  challenge's name takes one line or two.
- Leaderboard cards: every row ends at the page's right edge and cards are the same width across the groups of a row
  (three-card rows stopped ~60 px short).
- Match cards: "Combustion" + "Capture point · #id" wrapped and pushed that card's score and names a line down. Narrow
  cards now show "mode · #id" under the map name on every card; on a phone the Home list shows the match number
  instead of cutting it off.
- Match page and combat match: the Blue and Orange tables have the same column positions (were up to 28 px apart).
- Phones: labels sit on the line of their value in stacked tables ("Match", "Date", "Player" were half a line above
  their links); a player's loadout is one block with "+1 more" below it; the Home chart shows as many axis labels as
  fit (eight ran into each other).

**Home**
- The cards' comparison with the week before shows a drop in plain grey with a minus sign ("−20 pts vs the week
  before") instead of a red ▼; a rise stays a green ▲. The numbers are the same.

**To do after updating:** nothing. The first achievement ranking after this update is worked out from scratch once
(the code it depends on changed), in the background as usual. Two tests in `test_combat_achievements.py` fail before
and after this change (medal targets being re-tuned elsewhere); all others pass.

## 2026.11.16.19 — 14:00

- **Fixed: the "Compare" button on player profiles did nothing** (since 2026.11.16.12). The Compare page had moved into
  a Compare tab on the profile, but the tab itself was never added: the button, old `/compare` links and the
  Leaderboard's "Compare selected" all landed on the profile's Overview. The **Compare** tab is now there (last tab,
  always shown); the button opens it, other players are added by search (`?vs=`), the heatmap map is kept (`?cmp_map=`),
  and old links and "Compare selected" open it with their players and period.

## 2026.11.16.18 — 13:56

- **Home strip: a rolling week with trends instead of the calendar week.** "This week" restarted every Monday (on a
  Monday morning it was the same as "today", and 6 new players were compared with a whole week of 128).
  - **Matches · last 7 days** and **New players · last 7 days**: the last 7 days to the minute, the change against the
    7 days before (▲ green / ▼ red, grey within ±5 %), today's matches, and a line per day over the last 4 weeks.
  - **New players who came back**: also the change in points against the players new a week earlier.
  - Overview: new `trend` (`days`, `matches`, `new_players` per day for 28 days; `matches_7d`, `matches_prev_7d`,
    `new_7d`, `new_prev_7d`) and `newcomers.prev_return_rate`.
- **Home: "Most active this week" and "Combat this week" are one "This week" panel** with tabs: Most active (matches
  and win share, from the replays), Most kills and Most MVPs (top 5 each, from the recorder's match reports, which the
  panel says under those tabs). Same ranked rows with bars on every tab; the link follows the tab (Leaderboard / Combat
  leaderboard). All three still count from Monday (the Combat leaderboard has calendar periods only). On 1440p and 4K
  the panel runs down the right of both rows.
- **Home: "Players seen in Combat" is more compact:** the total and the "From the latest match" switch share one line
  (the exact dates are on hover) and the chart is 110 px tall instead of 180.

## 2026.11.16.17 — 13:47

- **Home "Latest matches": wider rows with more in them.** When the list is 620 px wide or more (any screen from a
  1366 px laptop up to 4K), each row shows the score and time on the left and, beside them, the tags (Close, Stomp,
  Full lobby, Combat report…) and up to 5 names per team, one line each (a name that does not fit is left out, never cut
  to "E…"). Narrow lists (phones) keep the short rows. `/api/overview/latest` and the overview's `latest` now carry the
  same card fields as the Matches page with names (`tags`, `player_count`, `players`), from one shared helper
  (`match_cards` in api/matches.py).
- **Player page: fewer hidden stats.** The stat cards fill one whole row before "More stats": 10 + More at 1080p
  instead of 6 + More (the first six are still Games, Win rate, Hours, Top / average speed, Wins – losses). Phones
  still show 6 + More.
- **Player page: more goals.** "Your goals" fills one row with goals: 5 at least (phones, as before), up to 20 on a
  wide screen (about 11 at 1080p), still the easiest next medals with at most 2 per theme first.

## 2026.11.16.16 — 13:41

- **Every page checked at 1080p, 1440p, 4K and phone size** (headless browser, snapshot data), to cut wasted space:
  - **Stat cards fill their row** on every page (player, match, home…): no empty columns on the right on a wide screen.
  - **Leaderboard:** the stat groups sit side by side while they fit: 3 rows of groups instead of 6 at 1440p (page 1,440 px tall instead of 2,127), and no empty right half.
  - **Home, 1440p and 4K:** video | latest matches | most active in one row, then players seen | Combat this week, so nothing is left empty beside the video.
  - **Match pages:** blue and orange team tables side by side when there is room: combat matches from about 1,900 px wide, replay matches (15 columns) on 4K.
  - **Phones:** fixed the home page's video and latest matches being squeezed side by side (the match cards were cut off at the screen edge). The tab rows on the match and player pages scroll sideways on purpose.

## 2026.11.16.15 — 13:36

- **Home: the live video and "Latest matches" now fill the whole row** on wide windows (no empty space on the right).
  The video takes half the row, up to 960 px wide, and the latest matches take the rest (one wide row per match since
  2026.11.16.17). Before, the row stopped at 1500 px unless the window was over 2100 px wide.

## 2026.11.16.14 — 13:24

- **Leaderboard (replay stats) redesign:**
  - **Opens on "All stats":** a card for every stat with its top 5, grouped (Activity, Movement, Teamwork, Objective, Social, Connection). Click a card's title or "Full board" for the whole ranking with the same filters (new `/api/leaderboard/overview`, from the same scan as the boards). Old `?stat=` links still open that board directly.
  - **Stat chips instead of the dropdown:** pick a group, then a stat in it.
  - **Records:** each player's best single match for top speed, distance, average speed, push time, block time, time inverted and emotes, with map, date and a link to the match (counted games only; average speed and time inverted also need a minute in the play area; new `/api/leaderboard/records`).
  - **Mode filter** (Capture point / Payload); the map list follows the mode.
  - **New stats:** *Distance travelled* (total km in the play area, from the per-frame speed), *Distance per game*, *Push time / Block time per payload game* (the minimum counts Payload games only), *Emotes per game*. No re-read needed.
  - **Podium:** gold, silver and bronze medals and accents, bigger pictures, the value large with its label, the context line smaller.
  - The "Compare selected" ticks stay on the full boards and are now kept when you switch between the cards, records and boards.

## 2026.11.16.13 — 13:22

- **Home page needs less scrolling** (2,315 px instead of 3,156 px at 1920×1080, 2.1 screens instead of 2.9; 3.3 instead of 4.0 at 1366×768):
  - Smaller gaps: a tighter header, no 32 px gap above panel headings, smaller section gaps, slimmer "Most active" rows.
  - The top row of cards fills the full width, so the labels stay on one line.
  - The Twitch video and latest matches split the row half and half (the video row is 448 px instead of 572 px).
  - Most active, Players seen and Combat this week sit side by side.
  - All time: the archive dates sit beside the heading, and the Archive, Fun facts, Records and More archive numbers groups sit side by side while they fit. More archive numbers is shown again instead of folded away.

## 2026.11.16.12 — 13:14

- **Matches list:**
  - **Summary strip** above the matches, following the filters: number of matches and average length, blue/orange win split, payload attack/defence split, share of close games and stomps, busiest map (new `/api/matches/summary`).
  - **Tags on each card:** *Close* (2–1; payload delivered with 30 s or less left, or held at the last checkpoint), *Stomp* (2–0; delivered with 3+ minutes left, or held before the first checkpoint), *Full lobby* (10+ players), *Combat report*, *Repaired*. Hover a tag for why it is there.
  - Player names split into **blue on the left, orange on the right**, and the cards are grouped under **day headings** (Today, Yesterday, Sat 7 Nov …, on your own clock).
- **Match page:**
  - **Match story** under the scoreboard: a bar across the match length with each round won (capture point) or checkpoint reached (payload) at its time, and the result at the end. Hidden for older replays without those events.
  - **Team comparison**: blue vs orange as mirrored bars: average speed, time near enemies and teammates, deaths, payload time, ping and level (replay data only; rates weighted by play time).

## 2026.11.16.11 — 13:13

- **Compare moved into the player profile and the Leaderboard; "Compare" removed from the top menu.**
  - Player profiles have a new **Compare** tab: that player is always the first column and their side of the head-to-head, with up to three others added by search. The **Compare** button in the profile header opens it. It follows the profile's period filter; the heatmaps keep their own map choice.
  - **Leaderboard (replay stats):** tick up to 4 players and press **Compare selected** to open the comparison on the first ticked player's profile. Ticks stay while you change stat, period, map or page, so players can be picked from different boards. The Combat board has no ticks (different data source).
  - Old `/compare?players=…` links still work: they open the first player's Compare tab with the others, period and map kept (no players: the Leaderboard).

## 2026.11.16.10 — 13:09

- **"Player not found" page:** its "All players" link (which only showed the 50 most recent players) now goes to the Leaderboard.

## 2026.11.16.9 — 13:07

- **"Players" removed from the top menu.** It only listed the 50 most recently seen players, which the search bar and Leaderboard already cover. The page stays as the search results page: press Enter in either search box to see every matching name. Old `/players` links still work.

## 2026.11.16.8 — 13:06

- **Home page redesign (layout option 2) with new stats:**
  - Top row: last match, matches today (this week underneath), **new players this week** (last week underneath), **new players who came back** (share of players first seen 8–14 days ago who played again on a later day within 7 days; 56 % in the 10 Nov snapshot), recently played.
  - **Combat this week:** a separate panel with the top 3 for kills and for MVP awards, from the game's own counters. It says it is a separate source from the replay stats.
  - Map cards show each map's **average match length**.
  - Gear row has a fourth card: the **most used full loadout** (weapon + ordnance + tac mod together; Nova + Detonator + Repair Matrix in the snapshot).
  - The 13-card "All time" block is now grouped: archive totals (average match split **per mode**), **Records**, a new **Fun facts** row (emotes used, time upside down, left-hand setting, players who left early), with recorded replay time and deaths (est.) under "More archive numbers".
  - Nothing to run: the overview is rebuilt by itself after the update.

## 2026.11.16.7 — 08:46

- **Permissions tab reworded:** Admin now says it includes the Preview and Cloud admin; Console says it includes the Preview but not the Cloud; Preview names what it opens (Echo Combat achievements, challenges and Mega Prizes before the launch date). Clearer intro, "User" instead of "User id" in the picker, and the remove question names the permission.

## 2026.11.16.6 — 08:25

- **Cloud admin is separate from the preview roles** (your choice): `ECHOVR_DISCORD_PREVIEW_ROLES` no longer gives Cloud admin. Cloud admin comes from the **Admin** permission (it includes Cloud admin now), the Cloud page, or the new `ECHOVR_DISCORD_CLOUD_ADMINS` in the YAML (role and / or user ids, cannot be removed on the page). If you were Cloud admin only through the preview roles, you now need one of those.
- **Way back into the Cloud:** the Cloud is separate from the Console, so an admin with no Cloud permission could not open the Cloud page to grant one. `admin.bat cloud-admins --add-user <your Discord user id>` makes a person Cloud admin (`--add-role` for a role; with no options it lists who is).

## 2026.11.16.5 — 08:16

- **Aggressive repair says why a replay cannot be saved** (checked on the 78 replays it was still failing on):
  - 60 are 0 to 44 MB of zero bytes (the disk wiped them) or empty: the list now says so, instead of "still failing after aggressive repair".
  - 11 still hold data, but the start of the recorded data is gone in both zip copies. A later block can be found, but every frame is stored as changes to the one before it, so each line stays unreadable (0 clean lines in a test on a good replay). Nothing is guessed, so they stay failed; hide them with `cannot-repair --hide`.
  - 8 `EchoRecorder/dist/...` paths are not on the share any more: `forget-missing` removes them.

## 2026.11.16.4 — 07:46

- **The Cloud is separate from the Console** (your choice):
  - A console user no longer has any Cloud access by being one. They see the Cloud only when given Cloud view, edit or admin, like anyone else.
  - **Cloud view / edit / admin are set on the Cloud page** ("All permissions" > "Who has the whole cloud"), by Cloud admins: click the box for a role or type a name, click the match; Remove takes it away. The Console's Permissions tab keeps only Admin, Console and Preview.
  - **Recycle bin, Quarantine and Audit log moved to the Cloud page**, as buttons for Cloud admins of the whole cloud. The Console's Cloud tab is gone.
  - The owner's ids in the YAML (the "YAML, fixed" role on the Permissions page) are always Cloud admin, so the cloud cannot be locked. A Cloud admin cannot remove their own Cloud admin by accident.
  - **Check after this update:** anyone who used the Cloud only because they are a console user (and is not in the YAML role) no longer sees the Cloud tab until a Cloud admin adds them. The Cloud view / edit / admin lists themselves are kept as they were.
- **The folder permissions box opens much faster.** It was asking Discord for every listed person's name and roles, one after another, before showing anything: 7.2 s for a folder with eight people in a measurement with a Discord that answers in 0.4 s. Now the names are asked side by side and the roles only when "Check: who gets in" is opened: 1.2 s the first time, 0.01 s after that (names are remembered until the site restarts). "All permissions" got the same change.

## 2026.11.16.3 — 07:24

- **Cloud permissions: security review, three holes closed** (found by reading the new code as an attacker would; none needed anything but an ordinary login with Edit somewhere):
  - **Upload into a folder you may not write to:** the folder was only checked when a file started uploading; the last piece of a file sent in pieces could name another folder, also a private one, and replace a file there. It is now checked again when the file lands.
  - **Two spellings of one name (NAS only):** permissions ignore upper / lower case, but the NAS keeps "Staff" and "STAFF" as two folders. Someone with Edit in a private folder could make the second spelling next to it and delete it again, which took the private folder's permissions with it. A name that differs only by case from one already in the folder is now refused everywhere (new folder, upload, rename, move, restore).
  - **Deleting or moving a folder that has permissions:** someone with only Edit in a private folder could delete it and make a new, open folder with the same name, or move a shared folder to where others see it. Deleting or moving a folder with its own permissions (or holding folders that have them) now needs its Admin. Files inside, and renaming, work with Edit as before.
  - Small ones: very long paths are refused before any check; searching people by name can use the Discord bot at most 30 times a minute, so it cannot use up what logins need.
  - Checked and found fine: other sites cannot trigger changes (every change needs this site's own header), a path cannot leave the cloud folder or dodge a rule with another spelling, names of hidden folders are never sent, nobody but a folder's Admin can read or change its permissions, and downloads still never run in the browser.
- **Layout fixes:** the Permissions page shows its six cards as two rows of three (was five and one left over), with the Discord id under the name and Remove at the right. The folder permissions box no longer has large empty gaps around the search box and is no wider than a form. The Cloud page has one row of buttons instead of two.

## 2026.11.16.2 — 07:15

- **Cloud: permissions per folder, three levels, and moving by drag and drop** (D61). Until now Cloud view / Cloud edit covered the whole cloud.
  - **Three levels:** **View** = download. **Edit** = also upload, new folder, rename, move and delete. **Admin** = also decides who gets into the folder. On the whole cloud these are Cloud view, Cloud edit and the new **Cloud admin** (Console > Permissions); console users have Cloud admin.
  - **Per folder:** an admin presses **Permissions** beside a folder on the Cloud page (or "Permissions of this folder" inside it). Click the box for the Discord roles, or type a name to find a person (players, people who used the cloud, the Discord server's members; a pasted Discord id works too) and click the match: added with View, saved at once. Change the level in the list, **Remove** takes someone out, both saved at once. No Save button.
  - It also works for people without any Cloud permission: they get the Cloud tab and see only the folders shared with them, plus the folders that lead there (nothing else in those).
  - **Private:** tick it and only the roles / people listed keep access; everyone else no longer sees the folder, also with Cloud view or Cloud edit. Someone listed with View can only download there. "New private folder" makes a folder that is private from the first moment.
  - **Files have no permissions of their own:** a file always follows the folder it is in. To change who sees a file, move it.
  - **Move by drag and drop:** drag the row of a file or folder onto a folder (or onto ".. (up one folder)" or a folder in the path at the top) to move it there. Needs Edit on the item and in the folder it goes to. A folder keeps its own permissions when moved. Dropping files from the PC still uploads, as before.
  - A folder's permissions apply to everything inside it; permissions on a folder further down win over the ones above. The exception: an Admin of a folder (or of the whole cloud) always sees and controls everything inside it, private or not. Rows show a **Private** / **Shared** tag, also when it comes from a folder above ("Private (from Staff)").
  - **Overview and checks for admins:** "All permissions" on the Cloud page (and Console > Permissions) lists every folder with its own permissions, with Open and Clear, and marks ones whose folder was removed with File Station. In a folder's permissions, "Check: who gets in" shows the final result for every role and person, "History" what happened to it (console users), and "Copy from" takes over another folder's list. Tick several folders to give them all the same permissions. **View as** shows a folder as a role or a person would see it.
  - Safety: rename, move and delete need Edit on the item and on everything inside it with its own permissions, so a private folder cannot be removed by deleting the folder around it. An admin cannot take their own Admin away by accident. Permissions follow a rename or move, and come back when a folder is restored from the recycle bin. The recycle bin, quarantine and audit log stay with console users. Every permissions change and move is in the Cloud audit log; refused attempts too.
  - Good to know: someone logged in sees a change within 5 minutes (at once after logging out and in). Names that differ only by upper / lower case share one set of permissions. Moving by drag needs a mouse (not on phones yet).
  - Nothing to do after the deploy: the new table is made by itself, and everything works as before until a permission is set.

## 2026.11.16.1 — 06:42

- **Cloud: first version of folder permissions.** Uploaded while it was still being built (it also allowed permissions on single files and had two levels). Replaced by 2026.11.16.2 the same morning; see there.

## 2026.11.14.2 — 02:59

- **Console warns about a match length that cannot be right:** when a replay is read and the match is zero / negative length, or more than 20 minutes longer than anyone was in it (what any jump of the recorder PC's clock looks like, not only the UK changes the reader now corrects), the replay gets a note, and `admin.bat status` lists them ("Match length looks wrong"). Only a note: the match is kept and counted as before. A long match with someone in it all the way is not flagged (the two longest in the archive, 55 and 62 minutes, are fine; checked on 33,500 matches: only the four daylight-saving ones trip it). Applies to replays read from now on; nothing is re-read.

## 2026.11.14.1 — 02:56

- **Matches played while the UK clocks changed now have the right length:** the recorder writes the PC's clock, so on the last Sunday of March (01:00 GMT -> 02:00 BST) a match running over the change looked an hour longer (match 213393: 67 minutes, really 7) and on the last Sunday of October (02:00 BST -> 01:00 GMT) an hour shorter, even negative (matches 223154, 214777, 211121). The reader now takes out exactly that one-hour step, only at those two moments; every other jump in a replay's clock is left alone. A note appears on the replay when it happens. `PARSER_VERSION` is unchanged, so nothing is re-read by itself: the four matches above (replays 27878, 27025, 28152, 21770) were found by searching the archive and are fixed once they are read again.

## 2026.11.13.2 — 19:32

- **Cloudflare tunnel connector updated to 2026.11.0** (`docker-compose.yml`; was 2026.10.7): Go update and a Cloudflare Access fix, nothing that changes how the site behaves. Already running on the NAS; the file now matches. Nothing to do.

## 2026.11.13.1 — 18:52

- **Search finds a match by its replay match ID:** paste the ID from the replay file (the session ID, any letter case) into the top-bar search and the match opens, just like `#12`. Part of the ID works too (at least 6 characters); up to 5 matches are listed, newest first. The site's own match numbers (`#12`) work as before. The search box hint now says so. No restart or re-read needed beyond the normal deploy.

## 2026.11.12.6 — 04:55

- **"Echo Unit Assassin" is now "Kronos II Assassin"** (user's choice): the challenge for winning the Assassin card
  in one game (the most kills). Only the name changed.
- **To do after updating:** restart the server.

## 2026.11.12.5 — 04:55

- **"Silent Assassin" is now "Echo Unit Assassin"** (user: the name should sound like Lone Echo / Echo VR / Echo
  Combat): the challenge for winning the Assassin card in one game (the most kills). Only the name changed.
- **To do after updating:** restart the server.

## 2026.11.12.4 — 04:54

- **"(Leaderboard)" after a challenge name is now "(Award card)"** (user): all 25 Combat challenges for winning an
  end-of-match award card, e.g. "Hot Streak (Award card)", "Most Valuable Jack (Award card)". Only the names changed.
- **To do after updating:** restart the server.

## 2026.11.12.3 — 04:53

- **Ten more award card challenges renamed** (user: a name must fit what the card is, not a map, weapon or gear item
  it has nothing to do with). Only the names changed: targets, progress and medals already earned stay.
  - Stun Field Lockdown → **Point Control** (Controller card, one game)
  - Detonator Strike → **Heavy Hitter** (Cannoneer card, one game)
  - Nova Strike → **Silent Assassin** (Assassin card, one game)
  - Comet Headhunter → **Headhunter** (Sniper card, one game)
  - Repair Matrix Rescue → **Field Medic** (Medic card, one game)
  - Repair Matrix on Call → **Medic on Call** (Medic card, any 7 days)
  - Repair Matrix Veteran → **Chief Medic** (total Medic cards; the old name was also the name of a gear challenge)
  - Dyson Defender → **Point Defender** (Defender card, one game)
  - Dyson Sentinel → **Sentinel** (total Guard cards)
  - Immovable Object on Dyson → **Immovable Object** (Immovable Object card, one game)
- **To do after updating:** restart the server.

## 2026.11.12.2 — 04:50

- **The two Hot Shot challenges renamed again** (user: the card is only the best elimination streak without dying,
  nothing to do with Combustion, maps or guns): "Combustion Hot Streak" is now **Hot Streak** (win the Hot Shot card
  in one game) and "Combustion Hot Shot" is now **Streak Master** (total Hot Shot cards won). Only the names changed.
- **To do after updating:** restart the server.

## 2026.11.12.1 — 04:49

- **Two Combat challenges renamed** (user: the Hot Shot card has nothing to do with the Pulsar): "Pulsar Streak" is
  now **Combustion Hot Streak** (win the Hot Shot card in one game) and "Pulsar Hot Shot" is now **Combustion Hot
  Shot** (total Hot Shot cards won). Only the names changed: targets, progress and medals already earned stay.
- **To do after updating:** restart the server.

## 2026.11.11.18 — 03:09

- **The small "cut" label is gone everywhere** (user; the home page heatmap choices lost it in 2026.11.10.48): gear
  names on player and match pages, the "Most popular gear" cards on the home page, and the "(cut)" after a name in
  the leaderboard's weapon, ordnance and tac mod filters. The hover text of a gear name now shows only its code. The
  data still says which gear is cut (`cut` in the API answers); nothing shows it.
- **To do after updating:** restart the server.

## 2026.11.11.17 — 03:03

- **Cyberkinetic Enhancements is harder again** (user): **2.6 / 2.85 / 3.1 / 3.4 m/s** (the previous update had made
  bronze 2 m/s, which every player with 25+ games reached). Bronze is back at 2.6, held by 68 % of regulars, then 41 /
  23 / 8 %; the steps are 0.25, 0.25 and 0.3 m/s.
- **Payload Pedal to the Metal is spread out** (user): **100 / 140 / 175 / 205 seconds** (was 112 / 182 / 198 / 207).
  The old top three were 9-16 seconds apart because almost every long push ends near 200 seconds. The crown is
  unchanged at about 7.5 % of regulars; regulars holding each medal: 75 / 51 / 23 / 9 % (was 69 / 20 / 11 / 8).
- **To do after updating:** restart the server.

## 2026.11.11.16 — 02:51

- **Seven ladders are less tight** (user): the medals were bunched together because these stats barely vary between
  players. The crowns stay (about 7.5 % of regulars); silver and gold step down, and bronze where needed, so every
  step is at least 8 % of the crown. The other five bunched ladders (top speed, Tech Support, Robot Wrecking Squad,
  Roboticide, Contested Point) already met that and are unchanged.

  | Achievement | Was | Now | Regulars holding each medal, was → now |
  |---|---|---|---|
  | Full Team Salvo | 40 / 55 / 60 / 67.5 % | 40 / 52.5 / 60 / 67.5 % | 51 / 20 / 15 / 8 → 51 / 31 / 15 / 8 |
  | Hug Your Frenemy | 10 / 11 / 12 / 13 % | 8 / 9.5 / 11 / 13 % | 41 / 29 / 16 / 10 → 69 / 47 / 29 / 10 |
  | The Wings of RAD_Wyvern | 2.75 / 3.25 / 3.5 / 3.65 m/s | 2.25 / 2.75 / 3.25 / 3.65 m/s | 59 / 25 / 16 / 8 → 93 / 59 / 25 / 8 |
  | Cyberkinetic Enhancements | 2.6 / 3 / 3.2 / 3.4 m/s | 2 / 2.5 / 3 / 3.4 m/s | 68 / 31 / 21 / 8 → 100 / 80 / 31 / 8 |
  | Marathon Bot | 12 / 14 / 16 / 17 min | 12 / 14 / 15.5 / 17 min | 88 / 57 / 29 / 8 → 88 / 57 / 34 / 8 |
  | Space Statue | 50 / 60 / 70 / 75 % | 50 / 60 / 67.5 / 75 % | 64 / 29 / 16 / 10 → 64 / 29 / 18 / 10 |
  | Boost Junkie | 3.5 / 4 / 4.5 / 4.75 m/s | 3.25 / 3.75 / 4.25 / 4.75 m/s | 79 / 42 / 15 / 9 → 90 / 59 / 25 / 9 |

  The price is a much easier bronze on Cyberkinetic (everybody who plays 25+ games has it) and Wings; the
  alternatives measured were stronger widening (every step 12 % of the crown) and raising the crown instead (which
  puts it at 0-4 % of regulars for five of them).
- **To do after updating:** restart the server.

## 2026.11.11.15 — 02:40

- **Achievement targets re-set so the top medal is reachable again** (user). The corrected bounds, spawn points and
  death rules (stats version 16) made many harder and left the crown of most with nobody; measured on the last 100
  days (1,529 matches, 819 players, 91 "regulars" with 25+ games).
  - **Skill and stat achievements** (speed, proximity, upside down, deaths, blocking, emotes ...): the crown is held
    by about **7.5 % of regulars** (about 7 of 91, under 1 % of all players), gold 12-15 %, silver about 20 %.
  - **Volume and activity achievements** (games played, per map, wins, hours, days, payload and capture point wins):
    the crown is held by about **5 % of regulars**, gold about 8 %, silver about 13 %. They keep a higher crown
    because they were set from the whole archive and are lifetime goals (user's choice, option B).
  - **Gear** (weapon, ordnance and tac mod): one set of numbers per kind of challenge, the same for all gear. Only the
    Veteran ones changed (5 / 15 / 25 / 40 games, was 5 / 19 / 29 / 49; the median gear now has its crown held by 7 %
    of regulars). "Only X in a day" and "only X in 7 days" were already at about 9 % and stay.
  - Unchanged on purpose: Lobby Mime Troupe (user), Quick-Change Chassis (a whole number of loadouts: 5 is held by 30 %
    and 6 by 2 %, nothing in between), the one-medal Untouchable Chassis and Test Drives, collections (Versatile Bot,
    5th Loadout, least-used gear), and the achievements already at 5 % or more.
  - Maps (4) and modes (2) keep identical numbers within each group.

  | Achievement | Was | Now |
  |---|---|---|
  | Full Team Salvo | 50 / 69 / 74 / 81% | 40 / 55 / 60 / 67.5% |
  | Can We Talk About This? | 25 / 35 / 40 / 50% | 20 / 25 / 30 / 40% |
  | Super Ultra Hyper Turbo | 14 / 20 / 26 / 30 m/s | 14 / 18 / 20 / 22 m/s |
  | I’m Bat Bot | 15 / 52 / 66 / 78% | 10 / 45 / 55 / 65% |
  | Tech Support w/RAD_Natalie | 16 / 24 / 26 / 28% | 16 / 19 / 21 / 23% |
  | Hug Your Frenemy | 12 / 16 / 18 / 20% | 10 / 11 / 12 / 13% |
  | The Wings of RAD_Wyvern | 2.75 / 3.25 / 3.5 / 3.75 m/s | 2.75 / 3.25 / 3.5 / 3.65 m/s |
  | I’ɯ ꓭɐʇ ꓭoʇ | 9.3 / 36 / 47 / 57% | 9 / 12 / 20 / 27% |
  | Pixel Party! | 205 / 810 / 1460 / 2470 | 150 / 600 / 1200 / 2000 |
  | King of the Hill | 14 / 54 / 95 / 165 | 14 / 54 / 90 / 105 |
  | Feed the Flamingo | 14 / 51 / 90 / 155 | 14 / 54 / 90 / 105 |
  | Robot Wrecking Squad | 14 / 17 / 25.4 / 29.2% | 12 / 14 / 16 / 18% |
  | Roboticide | 6 / 9 / 11 / 14% | 6 / 9 / 10 / 11% |
  | Cyberkinetic Enhancements | 2.6 / 3 / 3.2 / 3.5 m/s | 2.6 / 3 / 3.2 / 3.4 m/s |
  | toB taB m'I | 2 / 8 / 26 / 52% | 2 / 8 / 11 / 17% |
  | Brute Force Attack | 8 / 27 / 50 / 80 | 8 / 27 / 40 / 50 |
  | Molten Mechanical Mayhem | 7 / 26 / 49 / 80 | 8 / 27 / 40 / 50 |
  | George and I Go Way Back | 7 / 26 / 45 / 80 | 8 / 27 / 40 / 50 |
  | Good ol' George | 7 / 26 / 46 / 75 | 8 / 27 / 40 / 50 |
  | King/Queen of Pubs | 28 / 105 / 190 / 320 | 28 / 105 / 180 / 210 |
  | Centurion Bot (Wins) | 6 / 36 / 156 / 468 | 6 / 36 / 65 / 80 |
  | Capture Point Clean Sweep (Capture Point) | 1 / 12 / 39 / 156 | 1 / 12 / 18 / 22 |
  | Payload Delivered (Payload) | 1 / 12 / 39 / 94 | 1 / 11 / 18 / 21 |
  | Payload Shutout (Payload) | 1 / 12 / 39 / 94 | 1 / 11 / 15 / 20 |
  | Payload Roadblock (Payload) | 22 / 60 / 73 / 84 s | 22 / 45 / 60 / 70 s |
  | Payload Freight Train (Payload) | 3.3 / 15 / 25 / 46 min | 3.3 / 15 / 25 / 35 min |
  | Lobby Regular (Activity) | 10 / 31 / 47 / 75 | 10 / 14 / 19 / 25 |
  | Loyal Bot | 6 / 16 / 23 / 32 | 6 / 8 / 10 / 12 |
  | Ready Every Dawn (Activity) | 4 / 8 / 22 / 47 | 4 / 6 / 8 / 10 |
  | Time Well Wasted on Kronos II (Activity) | 3.5 / 14 / 26 / 43 h | 3.5 / 14 / 22 / 26 h |
  | Overtime on Kronos II (Activity) | 6 / 60 / 156 / 390 | 6 / 18 / 25 / 30 |
  | Hot Day Bot (Wins) | 3 / 8 / 16 / 23 | 3 / 8 / 12 / 15 |
  | Point Taker (Capture Point) | 6 / 36 / 125 / 234 | 6 / 22 / 30 / 40 |
  | Payload Hauler (Payload) | 6 / 36 / 125 / 234 | 6 / 22 / 30 / 40 |
  | Nothing Leaves Kronos II (Payload) | 2 / 36 / 94 / 187 min | 2 / 5.5 / 7 / 8.5 min |
  | Marathon Bot | 12 / 18 / 27 / 34 min | 12 / 14 / 16 / 17 min |
  | Capture Point Comeback (Capture Point) | 1 / 18 / 62 / 156 | 1 / 9 / 13 / 15 |
  | Space Statue (Movement) | 54 / 67 / 73 / 80% | 50 / 60 / 70 / 75% |
  | Lone Echo (Movement) | 94.6 / 98.2 / 99.1 / 100% | 93 / 97 / 98 / 99% |
  | Boost Junkie (Movement) | 3.5 / 4.5 / 5.25 / 6 m/s | 3.5 / 4 / 4.5 / 4.75 m/s |
  | Contested Point (Capture Point) | 2 / 5 / 8.5 / 10.4 min | 2 / 4 / 5 / 5.5 min |
  | Showbot (Emotes) | 4 / 8 / 10 / 14 | 4 / 6 / 7 / 8 |
  | All 19 gear Veteran achievements (every weapon, ordnance and tac mod: one set of numbers) | 5 / 19 / 29 / 49 games | 5 / 15 / 25 / 40 games |

  How many regulars hold each medal now (bronze / silver / gold / crown), for a few: Full Team Salvo 51 / 20 / 15 /
  8 %; Can We Talk About This? 42 / 19 / 14 / 8 %; Lone Echo 77 / 44 / 28 / 14 %; Boost Junkie 79 / 42 / 15 / 9 %;
  Wins (Centurion Bot) 90 / 17 / 9 / 8 %; King of the Hill 86 / 13 / 8 / 3 %; gear Veteran (median) 43 / 20 / 12 /
  7 %. They were worked out once from the local recent replays.
- Caveat: 69 % of the matches in that sample are from the last 13 days (81 a day, against 7 a day before), so the
  shares will move once the challenge has run for a month; the targets are worth another look then.
- **To do after updating:** restart the server.

## 2026.11.11.14 — 02:28

- **Full Team Salvo and Can We Talk About This?: the crown is easier, for about 7.5 % of regulars** (user: 3 % was
  too low). Measured on the last 100 days (91 regulars with 25+ games):
  - Full Team Salvo: **40 / 55 / 60 / 67.5 %** (was 40 / 55 / 65 / 75): 51 / 20 / 15 / 8 % of regulars hold each
    medal (before: 51 / 20 / 10 / 3).
  - Can We Talk About This?: **20 / 25 / 30 / 40 %** (was 20 / 25 / 35 / 50): 42 / 19 / 14 / 8 % of regulars (before:
    42 / 19 / 10 / 3).
- **To do after updating:** restart the server.

## 2026.11.11.13 — 02:21

- **Full Team Salvo and Can We Talk About This? are slightly easier** (user): bronze and silver only, gold and crown
  stay.
  - Full Team Salvo: **40 / 55 / 65 / 75 %** (was 45 / 60 / 65 / 75).
  - Can We Talk About This?: **20 / 25 / 35 / 50 %** (was 20 / 30 / 35 / 50).
  - Over the last 100 days the share of regulars (25+ games) holding each medal goes from 40 / 15 / 10 / 3 % to
    51 / 20 / 10 / 3 % for Full Team Salvo, and from 42 / 14 / 10 / 3 % to 42 / 19 / 10 / 3 % for Can We Talk About
    This?. Before the bounds were corrected the intended balance was about 56 / 18 / 10 / 4 %.
- **To do after updating:** restart the server.

## 2026.11.11.12 — 02:17

- **Untouchable Chassis counts games of 6 minutes or more** (user; it was 4). Measured on the last 100 days: with
  4 minutes 42 % of regulars (25+ games) held it, almost all from short games (zero-death games are 7.6 % of games
  of 4-6 minutes and 0.4 % of games of 8 minutes or more); with 6 minutes 21 % of regulars have it, 5 % three
  times. Still one medal, won or not.
- **New wording:** "Win a game without dying". What it needs is in the tags under it, as for the other
  achievements: "Best game · 6+ min games · 3+ players per team · 1+ min on the map" (the last tag is new: the
  minute on the map used to be in the sentence, which was why a player who never entered the map could not
  "win without dying").
- The other death achievements keep 4-minute games.
- **To do after updating:** restart the server.

## 2026.11.11.11 — 02:11

- **Pixel Party!: the top end is 2,000** (user), the other medals spread to match: **150 / 600 / 1,200 / 2,000**
  deaths for bronze / silver / gold / crown (150 / 500 / 900 / 1,500 in the previous update). Over the last 100
  days 72 players reach bronze (9 % of all players, 76 % of regulars), 12 silver, and nobody gold or crown: the
  most any player died was 990, about 10 a day, so 2,000 asks for roughly 200 days at that pace. A challenge
  period of 3-4 months will not get there at that rate; it is worth another look once the period has run for a
  month.
- **To do after updating:** restart the server.

## 2026.11.11.10 — 02:08

- **Pixel Party! is easier again** (user: slightly): 150 / 500 / 900 / 1,500 deaths for bronze / silver / gold /
  crown (was 200 / 750 / 1,350 / 2,250 two updates ago, 205 / 810 / 1,460 / 2,470 before the death rules were
  corrected). In the last 100 days nobody passed 990 deaths and 12 reached 750; with these targets 72 players hold
  bronze (9 % of all, 76 % of regulars with 25+ games), 15 silver, 2 gold, and the crown asks for half as much again
  as the best player did. A 3-4 month challenge period gives the best players more time than that sample.
- **To do after updating:** restart the server.

## 2026.11.11.9 — 01:59

- **The five achievements about deaths are worded more plainly** (the names, targets and how they are counted did
  not change):
  - My Other Chassis Is a Toaster: "Play games in which you die no more than 3 times" (was "Finish games with 3
    deaths or fewer").
  - Pew Pew Proof: "Play as many games in a row as you can while dying fewer than 5 times a game on average (within
    any 7 days, on at least 3 different days)" (was "Play games in a row, within any 7 days and on at least 3
    different days, that average fewer than 5 deaths per game").
  - Pixel Party!: "Your total number of deaths, all your games added up" (was "Total number of times you died,
    across all games").
  - Untouchable Chassis: "Win a game without dying a single time (you need at least 1 minute on the map)" (was "Win
    a game without dying once, with at least 1 minute in bounds").
  - Lobby Mime Troupe: "Use emotes in a game in which you never die: the more emotes, the higher the medal" (was
    "Use as many emotes as you can in one game without dying").
- **To do after updating:** restart the server.

## 2026.11.11.8 — 01:54

- **Seven achievements have new targets**, slightly easier than before and in round numbers (user). The corrected
  play-area bounds, spawn points and death rules (stats version 16) had made them harder: measured on the last 100
  days (1,545 matches, 819 players) by working out every achievement on the old and on the new stats.

  | Achievement | Was (bronze / silver / gold / crown) | Now | Players at or above each medal: before the corrections → with the new targets |
  |---|---|---|---|
  | Lone Echo | 94.6 / 98.2 / 99.1 / 100 % | 93 / 97 / 98 / 99 % | 181, 62, 33, 18 → 204, 68, 39, 17 |
  | Full Team Salvo | 50 / 69 / 74 / 81 % | 45 / 60 / 65 / 75 % | 64, 19, 11, 6 → 70, 23, 16, 6 |
  | I'm Bat Bot (one game) | 15 / 52 / 66 / 78 % | 10 / 45 / 55 / 65 % | 123, 38, 27, 22 → 146, 39, 28, 22 |
  | Space Statue | 54 / 67 / 73 / 80 % | 50 / 60 / 70 / 75 % | 115, 33, 19, 7 → 110, 42, 20, 12 |
  | Boost Junkie | 3.5 / 4.5 / 5.25 / 6 m/s | 3.5 / 4 / 4.5 / 5 m/s | 202, 38, 5, 3 → 218, 78, 22, 3 |
  | Can We Talk About This? | 25 / 35 / 40 / 50 % | 20 / 30 / 35 / 50 % | 63, 19, 15, 5 → 89, 24, 17, 6 |
  | Pixel Party! | 205 / 810 / 1,460 / 2,470 | 200 / 750 / 1,350 / 2,250 | 47, 9, 0, 0 → 46, 9, 0, 0 |

- Lobby Mime Troupe keeps its targets (user: easily done by somebody who sets out to). The other achievements that
  read the corrected numbers were left as they are; most of those got easier (Untouchable Chassis, Pew Pew Proof,
  Tech Support w/RAD_Natalie, The Wings of RAD_Wyvern, Super Ultra Hyper Turbo, Cyberkinetic Enhancements).
- **To do after updating:** restart the server. The medals follow the new targets as soon as the achievements are
  worked out again; the numbers themselves change as the archive is read again (stats version 16).

## 2026.11.11.7 — 01:33

- **New check: `app/tools/check_deaths.py`.** Counts the deaths of the newest replays twice, by the game's kill
  records and by the estimate from positions, and prints both per map with the matches where they are furthest
  apart. Read-only. Run on 12 recent matches a map: Combustion 279 by kills / 275 estimated, Dyson 311 / 314,
  Fission 304 / 304, Surge 215 / 224; the furthest a single match was apart: 5 deaths in 66. Worth running after a
  game or recorder update: the two should stay within a few percent.
- Correction to 2026.11.11.6: the 1-2 % of kills that name nobody among the listed players are not bots (there are
  none). They are players who dropped out of the match at that very moment: of 43 looked at, 33 never came back
  and 9 were back a minute or more later. The game writes a kill for it; it is not counted as a death.
- **To do after updating:** nothing beyond the restart and re-read of 2026.11.11.5.

## 2026.11.11.6 — 01:26

- **Deaths are the game's own kills wherever the recording has them** (user: build it if it makes current and
  future matches more accurate). Recordings from 4 November 2026 on carry the game's record of the latest kill
  (`last_kill`: who was killed, by whom, with what). For those matches a death is now a kill: counted at the
  moment and the place of the kill, with the killer and the weapon kept on the event. Every older replay keeps the
  estimate (a player leaving the map), the only thing it has.
- Why it is more accurate, measured on 100 recent matches (2,353 kills, 2,441 estimated deaths):
  - 96 % of the kills had their estimated death, always 6.5 to 6.95 s later;
  - 3 % of the estimated deaths were no kill at all (somebody leaving the map another way): no longer counted;
  - 4 % of the kills had no estimated death (the recording ended first, or the exit was not seen): now counted.
- One thing the record cannot show: the same player killed again by the same player with the same weapon leaves
  it unchanged. Those kills (about 4 % of all deaths) are taken from the estimate: a player leaving the map with
  no kill of theirs 6 to 7.5 s before, while the record still names them, was killed again.
- Over those 100 matches: Dyson 628 deaths (605 kills in the record + repeats), Combustion 608 (598), Fission 593
  (575), Surge 588 (575). A handful of kills name nobody among the players (1-2 %, in matches with a single
  player: a bot or somebody who had left) and are left out.
- Not changed: the death shows as before everywhere (deaths per match, heatmaps, timeline, achievements); the
  killer and the weapon are stored but not shown anywhere yet. Totals across the archive now mix the two methods:
  kills from 4 November 2026 on, the estimate before, which the checks above put within a few percent of each other.
- **The whole archive is read again after this update** (stats version 16, as 2026.11.11.5: still one pass).
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.11.5 — 00:54

- **Deaths now follow the round, as the game does: nobody can be killed once a round is won** (user). The round's
  end is the round score in the recorded API data going up; nothing is guessed from a clock of the app's own.
  - What the app counts as a death is the player leaving the map, and that comes 6.6 s after the kill (the killed
    player lies where they fell first; 95 % within 6.8 s). So a death up to 8 s after a round is won is a kill from
    just before it, and counts.
  - After those 8 s nobody leaving the map was killed. On capture-point maps everybody still on the map is moved to
    the war room about 18.65 s after the round; that was counted as 3.7 to 5.2 deaths a round, about 7 % of all
    deaths on Dyson. This lasts until 30 s after the round (the first players are back at 30.8 s), or to the end of
    the recording after the round that decides the match.
  - The round that decides the match: until now nothing after it counted at all, which also dropped the kills from
    just before it (about one a match). Those count again.
  - This replaces the rule of 2026.11.11.3-4 (a fixed window around 18.65 s) with one that needs no timing of the
    move itself.
- **Payload maps: a run no longer "ends" when the game timer first reaches zero.** Overtime follows while the
  attackers hold on, and a checkpoint reached in it sets the timer to 120 s again. The old rule (since stats
  version 9) dropped every death after that first zero: in 50 recent Fission and Surge matches about a fifth of
  all kills. A run now ends at its last checkpoint, or at the last moment either timer was running.
- **Checked against the game's own kill records.** The recorded API data has a `last_kill` field (who was killed,
  by whom, with what) that the app does not use for stats. Over 100 recent matches the deaths the app now counts
  are within +1 % to +6 % of those kills on all four maps (Dyson 638 against 605, Combustion 589 / 582, Fission
  624 / 593, Surge 621 / 593), typically 0 to 1 apart per match. Before these changes Fission and Surge were 10 %
  and 17 % short.
- Deaths change on every map, so everything that reads them moves (deaths per match, Pixel Party!, Pew Pew Proof,
  Untouchable Chassis, the Deaths heatmap, the death marks on the timeline).
- **The whole archive is read again after this update** (stats version 16; still one pass for everything since
  2026.11.10.43). The home page heatmaps count themselves again when it has finished.
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.11.4 — 00:22

- The move to the war room after a round (2026.11.11.3), measured exactly: it happens about **18.65 s** after the
  round is won. Over 8,388 such exits in 1,660 rounds the first player of a round leaves at 18.64 s (median), half
  of all exits fall between 18.65 and 18.72 s, 98 % between 18.55 and 20.0 s, the latest at 21.5 s. The spread
  comes from the recording (20 to 30 frames a second), not from the game. The window in which a death counts as
  that move now ends at 22 s instead of 20.5 s, so the few late ones are caught too (it starts at 17.5 s as before).
- **To do after updating:** restart the server, and expect the re-read (stats version 15, as 2026.11.11.3).

## 2026.11.11.3 — 00:17

- **The move to the war room after a round is no longer counted as deaths.** On the capture-point maps (Dyson,
  Combustion: best of three) everybody still on the map is moved to the war room 18.5 to 18.9 s after a round is
  won. When that round did not decide the match, each of those moves was counted as a death: 3.7 to 5.2 a round,
  about 7 % of all deaths on Dyson and 6 % on Combustion. A death 17.5 to 20.5 s after such a round is now that
  move, not a death.
  - Measured on 3,000 rounds from 2023 and 2026: the timing is the same in both. Matches from 2021 carry no round
    scores, so nothing changes for them.
  - Unchanged: after the round that decides the match nothing counted already (since stats version 9). The fight
    that goes on for some 7 seconds after a round is won, and the players coming back for the next round, still
    count as real deaths and respawns. Payload maps have no such move (a run is one round; checked: 0.4 % of
    their deaths fall in a second with four or more).
- Fewer deaths on Dyson and Combustion, so what reads them moves: deaths per match, Pixel Party!, Pew Pew Proof,
  Untouchable Chassis, the Deaths heatmap and the death marks on the timeline.
- **The whole archive is read again after this update** (stats version 15; still one pass for everything since
  2026.11.10.43). The home page heatmaps count themselves again when it has finished (2026.11.11.2).
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.11.2 — 00:11

- **The home page heatmaps count themselves again once the archive has been read again.** Nobody has to delete
  `map-heat*.npz` any more: the heat remembers the stats version its counts were made under, and when that is older
  than the app's and no replay is still waiting to be read again, the next visit to the home page starts a new
  count (all time: beside the old counts, swapped in when complete; the time ranges: from nothing, seconds). While
  the re-read is running it waits, looking again every 10 minutes; new recordings waiting for their first read do
  not hold it up.
- So after this update: restart, let the re-read finish, and the Deaths heatmap (corrected bounds, spawn points)
  follows by itself. The "delete the files" steps of the earlier entries are no longer needed.
- **To do after updating:** restart the server.

## 2026.11.11.1 — 00:03

- **The spawn points are now the measured ones** (the orange circles of the bounds editor, 2026.11.10.52), in
  place of the hand-drawn ones of 2026.11.10.51: Dyson 6, Fission 5, Surge 6, Combustion 2, each 1.5 m. A player who
  leaves the play area from inside one went back to the war room: not a death.
  - Combustion has one per side (the middle pod), not three; the hand-drawn circles of 4-10 m would also have
    hidden real deaths near the spawn points.
  - Dyson's two extra ones are the ends of the entry tubes along z = 0, at x = ±105. For them to count, **Dyson's
    bounds now reach x = ±110** (were ±100): the last 5 m of each tube is in bounds. Nothing else about the bounds
    changed: they stay boxes (the measured outline is not used, user).
- **The whole archive is read again after this update** (stats version 14; one pass covers this and everything
  since 2026.11.10.43). It starts by itself at the next start and takes hours on the NAS. Afterwards delete
  `data/database/map-heat*.npz` and open the home page for the new Deaths heatmap.
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.10.52 — 23:59

- **Bounds editor: it now opens with a measured outline and measured spawn points for every map**, from the
  latest 200 matches of each, to check and correct by hand ("Load measured" puts a map back to them; the dashed
  magenta line and crosses keep showing what was measured).
  - **Outline:** the part of the map players are on (cells visited at least 4 times, gaps up to 2.5 m closed,
    widened by 1.5 m, thinned to about 100-130 corner points a map). The ride from the load-in spot at (0, 0, 0)
    to the war room is left out; it drew a straight line across every map.
  - **Spawn points:** where players arrive on the map. They arrive within 0.7 m of fixed spots (Dyson 6,
    Fission 5, Surge 6, Combustion 2), and players walking back out leave from within about 1.5 m of them, so the
    circles are 1.5 m. Dyson has two more than the four in the middle: tubes along z = 0 that bring players in
    from x = ±105, outside its minimap picture (a third of the players of 200 matches used them).
- Nothing on the website changes with this update; the app still uses the boxes and the hand-drawn circles of
  2026.11.10.51 until the reviewed file is put in.
- **To do after updating:** nothing.

## 2026.11.10.51 — 23:51

- **Going back to the war room is no longer a death.** The spawn points of every map were drawn by hand in the
  bounds editor (Dyson 4, Fission 5, Surge 6, Combustion 6 circles). A player who leaves the play area from inside
  one went back by choice: no death is counted and no death is drawn there. Coming back out still shows as a
  respawn. Checked on Dyson, whose bounds were always right: 881 of its latest 71,641 estimated deaths (1.2 %)
  started inside one of its four circles, most within a metre of the middle.
- Fewer deaths on every map, so everything that reads them moves a little: deaths per match, Pixel Party!, Pew Pew
  Proof, Untouchable Chassis, death places on the heatmaps and the timeline. Time in bounds does not change.
- The circles are in `app/backend/stats/maps.py` (SPAWN_CIRCLES) and, the same numbers, in
  `app/tools/bounds_editor/echo_bounds.json` ("Open…" in the editor loads it to carry on drawing).
- No outlines were drawn: the play-area bounds stay the boxes of 2026.11.10.46.
- **The whole archive is read again after this update** (stats version 13; one pass covers this, the corrected
  bounds of .46 and the exact upside-down data of .43). It starts by itself at the next start and takes hours on
  the NAS. Afterwards delete `data/database/map-heat*.npz` and open the home page for the new Deaths heatmap.
- **To do after updating:** restart the server, and expect the re-read.

## 2026.11.10.50 — 23:45

- **Bounds editor: "Spawn circle" button** (or the C key). Drag on the map to draw a circle over a spawn point;
  drag its middle to move it, its edge to resize it, right-click to remove it. The circles mark where leaving the
  play area is the way back to the war room and must not count as a death. They are saved in `echo_bounds.json`
  under `"spawns": {"map": [[x, z, radius], ...]}`, beside the outlines. The app does not use them yet.
- **To do after updating:** nothing.

## 2026.11.10.49 — 23:41

- **New tool: the bounds editor** (`bounds_editor.bat`). Draw the play-area outline of each map by hand, over its
  minimap and over where players actually are (every position of the latest 400 matches per map, also beyond the
  picture). Click to place points, click the first point to close the outline, then drag points, click a line to
  add one, right-click to remove one; wheel zooms, right-drag moves the view. Green = inside, red = outside, the
  box now in the code as a dashed yellow line; x and z under the pointer.
- The work is kept in the browser while drawing; "Save" writes `echo_bounds.json` (`{"map": [[x, z], ...]}` in
  metres), which is what the app's bounds will be made from. Nothing on the website changes with this update, and
  the tool reads the data folder only (it writes one file of its own, `app/tools/bounds_editor/data.js`).
- **To do after updating:** nothing.

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
- **Still boxes, not the outline of each play area.** (Decided on 2026-11-11: they stay boxes; only the spawn
  points were added, 2026.11.11.1.)
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
