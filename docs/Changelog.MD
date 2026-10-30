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
