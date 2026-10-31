# Changelog

Working record of what changed in each release, newest first.

## Versioning (user, 2026-10-30)
- Every update gets the next **sequential beta number**: Beta 1, Beta 2, Beta 3, …
- The number lives in one place, `app/backend/version.py` (`BETA`). Bump it and add an entry at the top of this file
  in the same update. It is shown in the website footer, `/api/health` (`version`) and the admin console.
- `PARSER_VERSION` / `STATS_VERSION` are separate, internal: they decide which replays are re-read (D19) and are only
  bumped when parsing or stat calculation changes.
- Entry format: what changed for the person using the site / console, then anything they must do (restart, wait for
  a re-read).

---

## Beta 35 — 2026-10-31
### Website
- **The "Achievements" menu item says "Coming soon · 96"** before the Flamingo Challenge start date: the number of
  achievements and challenges available (hover for "96 achievements available"). The "Coming soon" page on
  /achievements names the number too. Previewers still see the "preview" tag instead.
- `/api/challenges` now includes `total`, the number of achievements, for everyone.

### Upgrading to Beta 35
- QNAP: upload Beta 35, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## Beta 34 — 2026-10-31
### Website
- **Player profiles no longer show "Achievements — coming soon"** before the Flamingo Challenge start date set in
  the console. The achievements section appears on profiles from the start date on (Discord preview-role members
  still see it early, as on the achievements page).

### Upgrading to Beta 34
- QNAP: upload Beta 34, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## Beta 33 — 2026-10-31
### Website
- **"Matches recorded over time" has a "Per day" tab** next to per month / per year. It shows the 90 days up to the
  newest recorded match (the archive may stop before today), one bar per day split by map, with days without
  matches left empty rather than skipped. Labels read "28 Oct", tooltips "28 October 2026". The whole archive per
  day would be ~1,600 bars, too thin to read.

### Upgrading to Beta 33
- QNAP: upload Beta 33, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## Beta 32 — 2026-10-31
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

## Beta 31 — 2026-10-31
### Website
- **Merged players no longer show up twice in the search box** at the top of the site. The Players page already
  hid them; the quick search still listed the merged ID with 0 games.
- **Old links to a merged ID open the main player's profile** (the address changes to the main player) instead of an
  empty profile with 0 games. Undoing the merge gives the ID its own profile back.

### Upgrading to Beta 31
- QNAP: upload Beta 31, wait for the Actions run, Recreate. Windows: restart `run.bat`. No re-import.

---

## Beta 30 — 2026-10-31
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

## Beta 29 — 2026-10-30
### Import
- **Reading a replay takes ~12 % less processor time** (parser and stats; same results, checked on 13 replays:
  stats, events and position files byte for byte). Helps where the processor is the limit (the NAS, 4 processes);
  no re-import.
- Measured on the PC: the import is limited by reading from the share (45-58 MB/s at its fastest, whether 2.6 or
  4.2 files/s), not by processing (8 processes could read ~700 MB/s), so it is not faster there.

### Upgrading to Beta 29
- QNAP: upload Beta 29, wait for the Actions run, Recreate. Windows: restart `run.bat`.

---

## Beta 28 — 2026-10-30
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

## Beta 27 — 2026-10-30
### Website
- **Home, "Matches recorded over time"**: one stacked bar per month (or year) split into the four maps (Combustion,
  Dyson, Fission, Surge), with a key above the chart; hovering a bar lists the matches on each map.
- **Home, "Most active this week"**: a ranked list instead of a table: gold / silver / bronze badges for the top
  three, a bar comparing each player's matches with the leader's, and win rate with the number of wins.

### Upgrading to Beta 27
- QNAP: upload Beta 27, wait for the Actions run, Recreate. Windows: restart `run.bat`.

---

## Beta 26 — 2026-10-30
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

## Beta 25 — 2026-10-30
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

## Beta 24 — 2026-10-30
### Website
- **Player profiles**: the **This is me / Not me** button and the **Export CSV · JSON** links are gone (user,
  2026-10-30). With "This is me" goes what it did: your own rank is no longer pinned above the leaderboard or
  highlighted in it, and Compare no longer adds "you" automatically. The player download
  (`/api/players/{user_id}/export`) and the leaderboard's `player` option are removed too. Match downloads stay.

### Upgrading to Beta 24
- QNAP: upload Beta 24, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## Beta 23 — 2026-10-30
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

## Beta 22 — 2026-10-30
### Website
- **Home page rearranged, most useful first**: search, then what is happening now (matches today, this week, how
  long ago the last match was, most played map), the **latest matches**, **most active this week** next to
  **players seen in Combat**, then matches per map, popular gear, and finally the **all-time** numbers (totals and
  global stats together) with the matches-over-time chart at the bottom. Nothing was removed.

### Upgrading to Beta 22
- QNAP: upload Beta 22, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## Beta 21 — 2026-10-30
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

## Beta 20 — 2026-10-30
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

## Beta 19 — 2026-10-30
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

## Beta 18 — 2026-10-30
### Website
- **Console page > Achievements > Export achievements and challenges**: every achievement and challenge with just
  its **Name** and **How to win it** (the rule text shown on the website; "(deaths are estimated)" where that
  applies). Filter the list, **Copy** it (pastes as two columns into Excel / Google Sheets) or **Download CSV**
  (`EchoVR-Achievements.csv`, always the full list). Console access only, checked with Discord on every request.

### Upgrading to Beta 18
- QNAP: upload Beta 18, wait for the Actions run, Recreate.
- Windows: restart `run.bat`.

---

## Beta 17 — 2026-10-30
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

## Beta 16 — 2026-10-30
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

## Beta 15 — 2026-10-30
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

## Beta 14 — 2026-10-30
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

## Beta 13 — 2026-10-30
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

## Beta 12 — 2026-10-30
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

## Beta 11 — 2026-10-30
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

## Beta 10 — 2026-10-30
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

## Beta 9 — 2026-10-30
### Website
- **Processing indicator**: while replays are still being read in the background, a small spinning wheel with
  "Processing N replays" shows in the top bar next to the site name, on every page. It checks every 15 seconds and
  disappears once everything is read. On phones only the wheel shows; tap/hover it for the count.
- New public endpoint `/api/overview/processing` (`{"pending": N}`) behind it.

### Upgrading to Beta 9
- Windows: restart `run.bat`.
- QNAP: upload Beta 9, wait for the Actions run, then Recreate the application in Container Station.

---

## Beta 8 — 2026-10-30
### Website
- **Long player names stay on one line**: in stat cards (home page Global stats, match page highlights) and on the
  leaderboard podium the name's text gets smaller until it fits the box. Extremely long names stop shrinking at a
  readable size and end in "…"; hover for the full name.
- **Match page highlights** (Fastest, Most mobile, …) stretch across the row, so long names fit at a normal size.

### Upgrading to Beta 8
- Windows: restart `run.bat`.
- QNAP: upload Beta 8, wait for the Actions run, then Recreate the application in Container Station.

---

## Beta 7 — 2026-10-30
### Website
- **Global stats** is back on the home page (https://echocombat.com), between "Most popular gear" and "Matches per
  map". The separate Global stats page and its menu entry are removed.
- **Home** menu entry, first in the menu: back to the home page from anywhere.

### Upgrading to Beta 7
- Windows: restart `run.bat`.
- QNAP: upload Beta 7, wait for the Actions run, then Recreate the application in Container Station.

---

## Beta 6 — 2026-10-30
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

## Beta 5 — 2026-10-30
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

## Beta 4 — 2026-10-30
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

## Beta 3 — 2026-10-30
### Server
- Can run on a QNAP NAS (or any Docker host): new `Dockerfile`, `docker-compose.yml` and `.dockerignore`. Pasting
  `docker-compose.yml` into Container Station downloads the app from GitHub, builds it and starts it; replays are
  mounted read-only, the database lives in a NAS `data` folder that survives updates.
- `upload_to_github.bat` also stops if any file to upload contains a GitHub token.

### Upgrading to Beta 3
- Windows: nothing to do; restart `run.bat` to see "Beta 3" in the footer.
- QNAP: upload Beta 3 to GitHub, then follow Setup.MD (QNAP NAS): token, folder paths, paste into Container Station.

---

## Beta 2 — 2026-10-30
### GitHub
- The replay share's network address is no longer in the repository: Setup.MD and Architecture.MD show a placeholder
  (`\\<server>\<share>\Replays`). Your own setup is unchanged (`Z:\ECRanked\Replays`, or `ECHOVR_REPLAY_SOURCE`).
- `upload_to_github.bat` also stops if any file to upload contains a local network address (192.168.x.x).

### Upgrading to Beta 2
- Nothing to do; restart `run.bat` to see "Beta 2" in the footer.

---

## Beta 1 — 2026-10-30
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
