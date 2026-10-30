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
| `ECHOVR_WORKERS` | `8` | Parallel processes for the import (PC has 24 cores) |
| `ECHOVR_SCAN_INTERVAL_S` | `300` | Seconds between scans of the share |

## Admin console
The website is read-only: every change is made with `admin.bat` (double-click it for a menu, or run it in a
terminal). It works on the database directly, so it needs no password and works with the server running or stopped.
Replays it queues go to the front of the queue: a running server picks them up within seconds, otherwise on its next start.

| Command | What it does |
|---|---|
| `admin.bat find <name or id>` | Find players |
| `admin.bat merge <keep> <other>...` / `merges` / `unmerge <merged id>` | Merge duplicate player records, list them, undo one |
| `admin.bat challenge --start 2026-01-01 --end 2026-01-31` (`--clear`) | Flamingo Challenge period |
| `admin.bat reprocess <replay id or path>` | Read one replay again |
| `admin.bat repair <replay id or path>` / `repair-failed` | Repair (salvage) damaged replays |
| `admin.bat cannot-repair [--hide]` / `hidden [--unhide <path> \| --unhide-all]` | Replays repair cannot fix: list, hide from the Import page, show again |
| `admin.bat scan` | Look for new files in the replay folder now |
| `admin.bat reprocess-all` | Rescan the folder, then read every replay again (about 3 hours; current results stay visible until replaced) |
| `admin.bat status` | Server, import progress (finished %, speed, time left), failures, player counts |

`--yes` skips confirmations; `admin.bat --help` lists everything. Names work as well as ids; an ambiguous name lists
the matches to pick from.

## Upload to GitHub
Double-click `upload_to_github.bat`. First time: create an **empty** repository at https://github.com/new (no README,
.gitignore or licence) and paste its address when asked; Git may open a GitHub sign-in window. Each run uploads the
application only, labelled with the beta version (`Beta N: <your description>`). Never uploaded (`.gitignore`): `data\`
(database, position tracks, exports), any `.echoreplay` / database file, `tests\sample-replays`, `docs\reference`,
`.venv`, `node_modules`, the built website. If one of those is ever about to be uploaded anyway, the script stops
before anything is sent. Needs Git for Windows (https://git-scm.com/download/win).

## QNAP NAS (Docker / Container Station)
Every upload to GitHub (`upload_to_github.bat`) makes GitHub Actions build the app image (`Dockerfile`: website +
server in one container) and publish it as `ghcr.io/vibinator/echocombat-replay-stats` (tags `latest` and
`beta-N`); watch it on the repository's **Actions** tab (a few minutes). The NAS only downloads that image: its Docker
has no `git`, so it cannot build from the repository itself.
1. Upload with `upload_to_github.bat` and wait for the Actions run to finish (green tick).
2. Token for downloading the image: GitHub > Settings > Developer settings > Personal access tokens >
   **Tokens (classic)** > Generate new token (classic). Note `QNAP ghcr`, scope **read:packages** only (fine-grained
   tokens cannot read packages). Copy it (starts with `ghp_`) and paste it nowhere but Container Station.
3. Container Station > Images (or Registry / Repository) > Add registry: URL `ghcr.io`, user name `vibinator`,
   password = the token.
4. Put the Cloudflare tunnel token in `docker-compose.yml` (`YOUR_CLOUDFLARE_TUNNEL_TOKEN`) and check the two NAS
   folders under `volumes`: the replay folder (File Station `ECRanked > ECRanked` = `/share/ECRanked/ECRanked`,
   read-only, subfolders included) and `data`. Set `ECHOVR_WORKERS` to about the NAS's core count.
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
   *Minimum TLS version* 1.2; Security > Bots > *Bot Fight Mode* on. Optional, Security > WAF > Rate limiting rule:
   URI path contains `/api/`, 100 requests per 10 seconds per IP > Block (heatmaps, playback and exports are the
   heaviest requests).
7. **Router / NAS**: no port forwarding for 8000 (or 80 / 443 to the NAS). Keep the NAS's own admin pages off the
   internet (myQNAPcloud / UPnP port forwarding off) - only the website is public, through the tunnel.

The website stays read-only to everyone: changes are only possible from the admin console in the container.

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
