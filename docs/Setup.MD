# Setup

Last updated: 2026-10-30 — Phase 6 (full website, `run.bat`).

## Prerequisites
- Python 3.12+
- Node.js 20+ and npm (tested with Node 24, npm 11)

## Quick start (Windows)
Double-click `run.bat` in `EchoVR-Replay-Stats\` (or run it from a terminal). First run creates `.venv` and installs packages (needs internet); every run rebuilds the website, starts the server and opens http://127.0.0.1:8000. Close the window (or Ctrl+C) to stop. The app reads replays from `Z:\ECRanked\Replays` by itself (no uploads): the first full import of ~29k files takes about 3 hours, newest first, so recent matches appear within minutes. Watch progress with `admin.bat status` (the website has no Import page). Stopping and restarting is safe and quick: finished replays are kept and never re-read (D27); it continues with whatever is still queued. Only an app update that changes how stats are calculated reprocesses replays, in the background, with the old results visible meanwhile.

## Install manually (from `EchoVR-Replay-Stats\`)
```
python -m venv .venv
.venv\Scripts\python -m pip install -r app\backend\requirements.txt
cd app\frontend
npm install
```

## Configuration
| Variable | Default | Purpose |
|---|---|---|
| `ECHOVR_DATA_DIR` | `<project>\data` | Database and processed files |
| `ECHOVR_REPLAY_SOURCE` | `Z:\ECRanked\Replays` | Read-only replay share (D25). Use the share's network (UNC) path, e.g. `\\<server>\<share>\Replays`, if `Z:` is not mapped for the account running the app |
| `ECHOVR_COMBAT_SOURCE` | the replay folder itself if it contains `matches\`, else the folder above it | Read-only recorder folder that contains `matches\` (combat stats, see CombatStats.MD). On the NAS (QNAP) it is the same share as the replays, `/share/ECRanked/ECRanked`, mounted at `/replays`: set `/replays` |
| `ECHOVR_COMBAT_SCAN_S` | `60` | Seconds between looks at `matches\` (one stat of the folder; `0` = combat stats off) |
| `ECHOVR_WORKERS` | `8` | Parallel processes for the import (PC has 24 cores) |
| `ECHOVR_SCAN_INTERVAL_S` | `300` | Seconds between full scans of the share |
| `ECHOVR_QUICK_CHECK_S` | `15` | Seconds between quick checks of the share's folders; a new file starts a full scan straight away (0 = off, full scans only) |
| `ECHOVR_PUBLIC_URL` | `http://127.0.0.1:8000` | Address people use; Discord sends them back to `<it>/api/auth/callback` |
| `ECHOVR_DISCORD_CLIENT_SECRET` | – | Discord login (D41). Secret: never in GitHub |
| `ECHOVR_DISCORD_BOT_TOKEN` | – | Bot that checks the preview role (D41). Secret: never in GitHub |
| `ECHOVR_BOT_LINK_SECRET` | – | Shared secret the Discord bot sends as `Authorization: Bearer <secret>` to link Discord accounts to players (D54). Unset = bot linking off. Secret: never in GitHub |
| `ECHOVR_REMOTE_WORKER_SECRET` | – | "Process replays on another PC" (see Remote processing): the PC sends it as `Authorization: Bearer <secret>`. Unset = the endpoints do not exist. Use a long random value; secret: never in GitHub |
| `ECHOVR_DISCORD_PREVIEW_ROLES` | – | Optional: role id(s) and / or Discord user id(s), comma-separated. Those people get the preview **and the website's Console page (admin.bat on the website, D45)**. For the preview alone use admin console option 14 |
| `ECHOVR_RATE_LIMIT_PER_MIN` | `60` | Scraper protection (D48): website data requests per visitor per minute, bursts up to twice that; heatmaps, playback, compare and downloads count 5. `0` = no limit |
| `ECHOVR_RATE_LIMIT_PER_HOUR` | `1500` | Same, per visitor per hour (no burst above it). `0` = no hourly limit |
| `ECHOVR_DB_CACHE_MB` | `1024` | RAM cache (D49): the database is memory-mapped up to this size and read in at startup. Shared OS file cache, given back when other programs need it. `0` = off |
| `ECHOVR_TRACK_CACHE_MB` | `512` | RAM cache (D49): decoded position files (heatmaps, playback), ~70 KB per match. App memory: lower it on a NAS with little RAM. `0` = off |
| `ECHOVR_CACHE_REFRESH_S` | `300` | Answer cache (D53): a page whose data changed is still answered at once and recalculated in the background at most this often (pages are at most about this far behind new replays). Lower = fresher, more CPU while importing. `0` = recalculate before answering (slow while importing) |
| `ECHOVR_RANKING_REFRESH_S` | `900` | The achievement ranking (achievement leaderboard, rarity shares, medal feed) is recalculated in the background at most this often; never more often than `ECHOVR_CACHE_REFRESH_S`. Its refresh reads every game of every player: the costliest one on the NAS (roughly 2-5 % of one core during play at 900, 6-14 % at 300). A player's own achievements page does not wait for it |
| `ECHOVR_EDGE_CACHE_S` | `60` | Cloudflare may keep public data answers this many seconds, so repeats never reach the NAS (needs the Cache Rule, see Cloudflare cache). Login answers and errors are never kept. `0` = Cloudflare never keeps them |
| `ECHOVR_DISCORD_NAME_PICTURES` | `1` | Player pictures matched by name from the Discord server's member list. Needs the bot's **Server Members intent** (Developer Portal > Bot > Privileged Gateway Intents; no approval needed while the bot is in fewer than 100 servers). Without it Discord's refusal is logged once per start and nothing else changes. `0` = never ask for the member list. Pictures of linked players and known Discord ids need no intent either way |
| `ECHOVR_CLOUD_TRASH_DAYS` | `30` | Open Cloud: deleted files and folders stay this many days in the recycle bin (Console > Cloud > Recycle bin), then go for good. `0` = kept until a console user removes them. The recycle bin counts toward the quota |
| `ECHOVR_CLAMAV` | – | Virus scan of cloud uploads (antivirus.py): ClamAV's daemon as `host:port`, `clamav:3310` with the `clamav` service of docker-compose.yml. Unset = no scanning. Files up to `ECHOVR_CLAMAV_MAX_MB` are held ("Checking for viruses") until clean |
| `ECHOVR_CLAMAV_MAX_MB` | `100` | Bigger files are not scanned and are labelled "Not scanned". Raising it also needs ClamAV's own `MaxFileSize` / `MaxScanSize` raised (more RAM and time): the NAS YAML sets 1024 here and `MaxFileSize 1024M` / `MaxScanSize 2048M` on the clamav service (ClamAV's ceiling is 2 GB) |
| `ECHOVR_VIRUSTOTAL_KEY` | – | VirusTotal fingerprint check of cloud files (only the SHA-256 is sent). Free key from virustotal.com. Secret: never in GitHub (upload_to_github.bat refuses it) |
| `ECHOVR_VIRUSTOTAL_MIN_ENGINES` | `3` | Engines that must call a file malicious before it is quarantined (one or two alone are often false alarms) |
| `ECHOVR_CLOUD_QUOTA_GB` | `250` | Open Cloud (D60): at most this many GB of files in `<data>/cloud`. `0` = no limit (an upload still never leaves less than 5 GB free on the disk) |
| `ECHOVR_DISCORD_CLIENT_ID` / `_GUILD_ID` | `1214456381466222683` / `779349159852769310` | Bot application and EchoVR Combat server |

## Admin console
The website is read-only: every change is made with `admin.bat` (double-click it for a menu, or run it in a
terminal). It works on the database directly, so it needs no password and works with the server running or stopped.
Replays it queues go to the front of the queue: a running server picks them up within seconds, otherwise on its next start.

| Command | What it does |
|---|---|
| `admin.bat find <name or id>` | Find players |
| `admin.bat merge <keep> <other>...` / `merges` / `unmerge <merged id>` | Merge duplicate player records, list them, undo one |
| `admin.bat challenge --start 2026-01-01 --end 2026-01-31` (`--clear`) | Flamingo Challenge period. The start date is the launch date: achievements and challenges are "Coming soon" on the website until then (D40) |
| `admin.bat preview-roles [--server] [--add <role id>] [--remove <role id>]` | Discord roles whose members see achievements before the launch (menu option 14 lists the server's roles to pick from; needs the bot token) |
| `admin.bat admin-roles [--server] [--add <role id>] [--remove <role id>]` | Discord roles that get the website's **Admin** tab: achievement list + Excel download, and changing achievement icons (menu option 15) |
| `admin.bat admin-users [--add <user id>] [--remove <user id>]` | Discord **people** (Copy User ID) who get the Admin tab and the preview, whatever their roles. Menu option 17 |
| `admin.bat discord-check <discord user id>` | What the bot sees for one person: in the server or not, their roles, whether they get the Admin tab / preview, and what is wrong (bad bot token, bot not in the server, no admin role set). Menu option 16 |
| `admin.bat reprocess <replay id or path>` | Read one replay again |
| `admin.bat repair <replay id or path>` / `repair-failed` | Repair (salvage) damaged replays |
| `admin.bat cannot-repair [--hide]` / `hidden [--unhide <path> \| --unhide-all]` | Replays repair cannot fix: list, hide from the Import page, show again |
| `admin.bat forget-missing` | After the replay folder was moved (`ECHOVR_REPLAY_SOURCE` changed) or files were deleted: forgets the replay rows whose file is no longer under the folder, with their matches (players stay; the same matches under their new path keep showing). Refuses while the folder is offline. Also in the Console, Replays tab |
| `admin.bat remote [--on \| --off]` | Read replays on another PC (`remote_worker.bat`) instead of on this server; no option shows the setting and when the PC last asked for work. Menu option 21 |
| `admin.bat scan` | Look for new files in the replay folder now |
| `admin.bat reprocess-all` | Rescan the folder, then read every replay again (about 3 hours; current results stay visible until replaced) |
| `admin.bat status` | Server, import progress (finished %, speed, time left), failures, player counts |

`--yes` skips confirmations; `admin.bat --help` lists everything. Names work as well as ids; an ambiguous name lists
the matches to pick from.

## Upload to GitHub
Double-click `upload_to_github.bat`. First time: create an **empty** repository at https://github.com/new (no README,
.gitignore or licence) and paste its address when asked; Git may open a GitHub sign-in window. Each run uploads the
application only, labelled with the beta version (`Beta N: <your description>`). Never uploaded (`.gitignore`): `data\`
(database, position tracks, exports), any `.echoreplay` / database file, `tests\sample-replays`, the old-site files in `docs\reference` (minimaps, extract, gear table; the code maps there are uploaded),
`.venv`, `node_modules`, the built website. If one of those is ever about to be uploaded anyway, the script stops
before anything is sent. Needs Git for Windows (https://git-scm.com/download/win).

## QNAP NAS (Docker / Container Station)
Every upload to GitHub (`upload_to_github.bat`) makes GitHub Actions build the app image (`Dockerfile`: website +
server in one container) and publish it as `ghcr.io/vibinator/echocombat-replay-stats` (tags `latest` and
the app version, e.g. `2026.11.01.6`; older images are tagged `beta-N`); watch it on the repository's **Actions** tab (a few minutes). The NAS only downloads that image: its Docker
has no `git`, so it cannot build from the repository itself.
1. Upload with `upload_to_github.bat` and wait for the Actions run to finish (green tick).
2. Token for downloading the image: GitHub > Settings > Developer settings > Personal access tokens >
   **Tokens (classic)** > Generate new token (classic). Note `QNAP ghcr`, scope **read:packages** only (fine-grained
   tokens cannot read packages). Copy it (starts with `ghp_`) and paste it nowhere but Container Station.
3. Container Station > Images (or Registry / Repository) > Add registry: URL `ghcr.io`, user name `vibinator`,
   password = the token.
4. Put the Cloudflare tunnel token in `docker-compose.yml` (`YOUR_CLOUDFLARE_TUNNEL_TOKEN`) and check the two NAS
   folders under `volumes`: the replay folder (File Station `ECRanked > ECRanked` = `/share/ECRanked/ECRanked`,
   read-only, subfolders included) and `data`. Set `ECHOVR_WORKERS` to about half the NAS's core count (2 on a 4-core NAS keeps the pages quick while replays are read; all cores read faster but the site shows "Server busy").
5. Container Station > Applications > Create, name it `echovr-replay-stats`, paste the edited YAML, Create.
6. Open `http://<nas address>:8000`. The first import of all replays takes longer than on the PC.

Update to a new beta: upload it, wait for the Actions run, then in Container Station open the application and
Recreate / redeploy it (`pull_policy: always` downloads the new image). The `data` folder is kept.

Admin console: Container Station > Containers > echovr-replay-stats > Terminal, then `python app/admin_console.py`
(add a command, e.g. `status`), or over SSH `docker exec -it echovr-replay-stats python app/admin_console.py`.

## Public website: echocombat.com (Cloudflare Tunnel)
The NAS reaches out to Cloudflare (the `cloudflared` container in `docker-compose.yml`); visitors go to Cloudflare,
which passes requests down that connection. No ports are opened on the router, the home IP address is never shown,
Cloudflare provides HTTPS and blocks attacks. Free plan. The domain stays registered (and renewed) at GoDaddy; only its
DNS moves to Cloudflare.
1. **Cloudflare account**: sign up at https://dash.cloudflare.com, *Add a domain* > `echocombat.com` > Free plan.
   It copies the existing DNS records from GoDaddy: keep any email (MX / TXT) records, delete old `A` / `CNAME`
   records for `echocombat.com` and `www` (the tunnel replaces them). Cloudflare shows two nameservers.
2. **GoDaddy**: My Products > echocombat.com > DNS. If DNSSEC is on, turn it off first. Nameservers > Change >
   *I'll use my own nameservers* > enter Cloudflare's two > Save. Cloudflare emails when the domain is active
   (minutes, at most 24 hours).
3. **Tunnel**: Cloudflare > Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared > name `echocombat`.
   On the install page choose Docker and copy only the token (the long value after `--token`, starts with `eyJ`).
4. **Public hostnames** (next page of the tunnel): `echocombat.com` > Service HTTP, URL `echovr-replay-stats:8000`;
   add a second one for `www.echocombat.com` with the same service.
5. **NAS**: the tunnel token goes in `docker-compose.yml` (`YOUR_CLOUDFLARE_TUNNEL_TOKEN`, QNAP NAS step 4). The tunnel page shows *Healthy*; open https://echocombat.com.
6. **Cloudflare settings** for echocombat.com: SSL/TLS > Edge Certificates > *Always Use HTTPS* on and
   *Minimum TLS version* 1.2; Security > Bots > *Bot Fight Mode* on and *Block AI bots* (AI Scrapers and Crawlers)
   on. Optional, Security > WAF > Rate limiting rule: URI path contains `/api/`, 100 requests per 10 seconds per IP
   > Block (heatmaps, playback and exports are the heaviest requests). The app has its own limits behind these
   (scraper protection, D48), so these settings stop most bots before they reach the NAS at all.
7. **Router / NAS**: no port forwarding for 8000 (or 80 / 443 to the NAS). Keep the NAS's own admin pages off the
   internet (myQNAPcloud / UPnP port forwarding off) - only the website is public, through the tunnel.

The website stays read-only to everyone: changes are only possible from the admin console in the container.

## Cloudflare cache (D53)
Cloudflare keeps public data answers for `ECHOVR_EDGE_CACHE_S` (60 s), so repeated requests never reach the NAS. The
app decides what may be kept, in a header only Cloudflare reads (`Cloudflare-CDN-Cache-Control`): answers that depend
on who is logged in, and errors, are never kept; browsers always check with the server (`no-cache` + ETag). Static
files (scripts, styles, images) were already kept by Cloudflare and need nothing. Free plan.
1. **Cache Rule**: Cloudflare dashboard > echocombat.com > Caching > Cache Rules > *Create rule*. Name `API answers
   (the app decides)`.
2. **When incoming requests match**: *Custom filter expression* > *Edit expression*, paste
   ```
   (starts_with(http.request.uri.path, "/api/") and any(http.request.headers["x-echovr"][*] == "1"))
   ```
   The header part keeps the app's scraper check in front of cached answers: a request without the site's own
   header is never answered from the cache, so it still reaches the app and is refused (D48). If the editor refuses
   the header field, use `starts_with(http.request.uri.path, "/api/")` alone; cached answers can then be read without
   the header (rate limited by step 4).
3. **Then**: *Cache eligibility* = **Eligible for cache**; *Edge TTL* = **Use cache-control header if present, bypass
   cache if not** (never *Ignore cache-control header and use this TTL*: login answers would be shared between
   visitors); *Browser TTL* = **Respect origin**. Leave the rest as it is (*Serve stale content while revalidating*
   on, *Respect strong ETags* off, cache key default). *Deploy*.
4. **Rate limiting** (now recommended: cached answers never reach the app's own limit): Security > WAF > Rate limiting
   rules > *Create rule*: URI Path contains `/api/`, same characteristics (IP), 100 requests per 10 seconds, action
   Block for 10 seconds. A normal page asks 5-10 at once.
5. **NAS**: `docker-compose.yml` has `ECHOVR_EDGE_CACHE_S: "60"` and `ECHOVR_CACHE_REFRESH_S: "300"` (the defaults);
   change them there and Recreate. `ECHOVR_EDGE_CACHE_S: "0"` turns the Cloudflare part off without touching the rule.
6. **Check**: double-click `check_cloudflare.bat` (or on the NAS: `docker exec -it echovr-replay-stats python
   app/cloudflare_check.py https://echocombat.com`). It asks the site about 20 small questions, changes nothing, and
   says PASS / WARN / FAIL with what to fix. All PASS = done. A login answer served from the cache is reported as
   DANGER: fix step 3 at once.

**Check in a browser** (if Cloudflare challenges the check): open https://echocombat.com, F12 > Network, reload, click
`overview`: *Response headers* show `cf-cache-status: HIT` (or `MISS` on the first visit within 60 s), `etag`, and
`cache-control: no-cache`. `me` (the login answer) must never say `HIT`.

After an admin change (merge, challenge period) Cloudflare can show the old answer for up to 60 s and the server for
up to 5 minutes; nothing needs purging. Caching > Configuration > *Development Mode* bypasses Cloudflare's cache for
3 hours when needed.

## Remote processing (read replays on a PC instead of the NAS)
Reading replays is slow on the NAS. Another Windows PC with the replay share connected can do it:
1. **On the NAS:** add `ECHOVR_REMOTE_WORKER_SECRET: <a long random value>` to the application's environment in the compose file and recreate the application.
2. **On the PC:** have the app at the same version as the website (`git pull`, then `run.bat` once), and create `settings.local.bat` (never uploaded) with
   ```
   set ECHOVR_REMOTE_WORKER_SECRET=<the same value>
   set ECHOVR_REMOTE_SERVER=https://echocombat.com
   set ECHOVR_REPLAY_SOURCE=Z:\ECRanked\Replays
   ```
   `ECHOVR_REMOTE_SERVER` may also be the NAS's address on the home network (`http://<nas>:8000`): faster, and it does not go through Cloudflare.
3. **Turn it on:** Console > *Process replays on another PC* (or `admin.bat remote --on`). From then on the NAS reads no replays itself.
4. **Run `remote_worker.bat`** on the PC (all cores but two; `--workers N` changes that). It prints what it does; Ctrl+C stops it and gives unfinished replays back.
5. **Turn it off** with *Process replays on this server again* (or `admin.bat remote --off`) when the PC is not running: until then nothing is read (the Console status says when the PC last asked for work).

Good to know: the PC only reads and sends results; the NAS is the only one that writes to the database. If the PC cannot see a file, it gives the replay back instead of marking it failed. A replay the PC claimed and never answered is queued again after 30 minutes. If Cloudflare turns the PC's requests away (bot protection), use the NAS's home-network address.

## Discord login (achievement previews, D41)
Before the achievements launch date (admin console option 5), members of the Discord server
779349159852769310 with a preview role can log in and see achievements and challenges; everyone else sees "Coming
soon". The login is off until the client secret and bot token are set; preview roles are picked in the admin
console (option 14, or `admin.bat preview-roles`).
1. **Developer Portal** (https://discord.com/developers/applications) > the bot's application
   (1214456381466222683) > OAuth2 > Redirects: add `https://echocombat.com/api/auth/callback` and
   `http://127.0.0.1:8000/api/auth/callback`. Copy the **Client Secret** (Reset Secret if you never copied it).
2. **Bot token**: the bot's existing token (Bot page). The website only asks Discord about members with it; it does
   not connect as the bot, so the bot keeps working. Resetting the token means updating the bot too.
3. **NAS**: in Container Station > the application > edit, replace `YOUR_DISCORD_CLIENT_SECRET` and
   `YOUR_DISCORD_BOT_TOKEN` (leave `YOUR_PREVIEW_ROLE_ID` as it is), then Recreate.
4. **Windows (`run.bat`, `admin.bat`)**: create `settings.local.bat` next to `run.bat` (never uploaded):
   ```bat
   set ECHOVR_DISCORD_CLIENT_SECRET=...
   set ECHOVR_DISCORD_BOT_TOKEN=...
   ```
5. **Preview roles**: admin console option 14 lists the server's roles (via the bot); type the number of the role
   to add it, `-` + number to remove it. Kept across database rebuilds. The bot must be in the server (no
   permissions needed). Without the bot token on that computer, enter the role id instead (Discord: Developer
   Mode on, Server Settings > Roles > right-click the role > Copy Role ID).

Player pictures: looked up one person at a time with the bot (no special permission), only when someone opens that
player's profile page (lists show saved pictures and never ask Discord), remembered 24 hours in
`data/discord-avatars.json` so restarts and updates do not ask Discord again; a player saving their profile refreshes theirs at once.
Matching pictures to unlinked players by name also needs the bot's Server Members intent (see `ECHOVR_DISCORD_NAME_PICTURES`).

Discord limits (auth.py `DiscordLimiter`): every Discord request of the site together stays at most 5 a second (a tenth
of Discord's 50 per bot; the site shares the token with the Discord bot), a 429 pauses all of them for Discord's
Retry-After, and 500 refused requests in 10 minutes stop them for 10 minutes (Discord blocks an IP at 10,000).

Giving or removing the role in Discord takes effect within 5 minutes. A login lasts 30 days; deleting
`data/session.key` logs everyone out.

### Open Cloud (file storage, D60)
The **Cloud** tab (`https://echocombat.com/cloud`) shows only to people logged in with Discord who have a Cloud
permission. Give it on Console > Permissions: **Cloud view** = see and download files, **Cloud edit** = also upload,
make folders, rename and delete. Console users have both. Files are kept on the NAS in the data folder
(`/share/Container/echovr-replay-stats/data/cloud`), so they survive app updates; File Station can also reach them
there. Space: `ECHOVR_CLOUD_QUOTA_GB` (250 GB by default, for everyone together). Big files are sent in 16 MB pieces, so Cloudflare's
100 MB limit does not apply. Every upload, download, change and refused attempt is in Console > Audit log >
Cloud audit log (who, when, file, size, IP; console users only) and in the container log.
Virus scanning: the `clamav` service in docker-compose.yml (about 1.2-1.6 GB RAM; its virus list is kept in
`/share/Container/echovr-replay-stats/clamav`, and it reads the app's data folder read-only at the same path `/data`).
Uploads up to 100 MB wait as "Checking for viruses" until ClamAV calls them clean; a VirusTotal fingerprint check follows in
the background when `ECHOVR_VIRUSTOTAL_KEY` is set. Finds go to Console > Cloud > Quarantine (delete, or release a false
alarm). After setting it up, press **Scan all existing files** there once. Check it works: upload the standard EICAR test
file (eicar.org); it must end up in the quarantine.

## Run (single server)
```
cd app\frontend
npm run build
cd ..\..
.venv\Scripts\python -m uvicorn backend.main:app --app-dir app --port 8000
```
- Site: http://127.0.0.1:8000 — the backend serves the built frontend from `app\frontend\dist`.
- Health: http://127.0.0.1:8000/api/health — API docs: http://127.0.0.1:8000/docs
- Database is created on first start at `data\database\echovr-stats.db`.

## Run frontend (development, hot reload)
Start the backend as above, then:
```
cd app\frontend
npm run dev
```
Open http://127.0.0.1:5173 — `/api` is proxied to the backend on :8000.

## Tests
```
.venv\Scripts\python -m pytest
```
- Tests use a temporary data folder; real `data\` is never touched.
- Parser tests also run on the two real replays in `tests\sample-replays\` (small files only, ≤ ~5 MB).
- Frontend type-check + build: `npm run build` in `app\frontend`.

## Disk use
- `data\processed\` holds one small position file per replay (≈ 20 KB; ≈ 0.6 GB for the full archive), used by heatmaps and timelines.
- `data\database\` ≈ a few hundred MB for the full archive.

## Reset local data
- Stop the server, then delete `data\database\echovr-stats.db*` (incl. `-wal`, `-shm`) and the contents of `data\processed` / `data\exports`. The next start re-imports everything from the share (~3 h). The share itself is never touched.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: backend` | Run uvicorn with `--app-dir app`, from the project root |
| Import page: "Replay folder not reachable" | Check `Z:` is connected (open it in Explorer), or set `ECHOVR_REPLAY_SOURCE` to the UNC path; the app retries every 5 min |
| Many `failed` / `unreadable` on Import | Network dropped mid-read: fix the connection, then restart (failed rows are retried only after reprocess or upgrade) |
| Page says "Could not reach the server" | Start the backend on :8000 |
| Old page after frontend changes | Re-run `npm run build` (single-server mode) |
| `run.bat`: "python is not recognized" | Install Python 3.12+ and tick "Add to PATH" |
| `run.bat`: "npm is not recognized" | Install Node.js 20+ |
| Port 8000 already in use | Close the other server window, or change `--port` in `run.bat` |
| `database is locked` | Only one server instance per data folder |
| A damaged replay failed | Import page → Failed → **Repair** (or Repair all); the original file is not changed |
| A replay shows `failed` | See the reason on the Import page: `unsupported`, `corrupt`, `incomplete`, `unreadable`, `crashed` |
