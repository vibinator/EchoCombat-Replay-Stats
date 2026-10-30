# Setup

Last updated: 2026-10-30 — Phase 6 (full website, `run.bat`).

## Prerequisites
- Python 3.12+
- Node.js 20+ and npm (tested with Node 24, npm 11)

## Quick start (Windows)
Double-click `run.bat` in `EchoVR-Replay-Stats\` (or run it from a terminal). First run creates `.venv` and installs packages (needs internet); every run rebuilds the website, starts the server and opens http://127.0.0.1:8000. Close the window (or Ctrl+C) to stop. The app reads replays from `Z:\ECRanked\Replays` by itself (no uploads): the first full import of ~29k files takes about 3 hours, newest first, so recent matches appear within minutes. Watch progress on the **Import** page. Stopping and restarting is safe and quick: finished replays are kept and never re-read (D27); it continues with whatever is still queued. Only an app update that changes how stats are calculated reprocesses replays, in the background, with the old results visible meanwhile.

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
| `admin.bat status` | Server, replay and player counts |

`--yes` skips confirmations; `admin.bat --help` lists everything. Names work as well as ids; an ambiguous name lists
the matches to pick from.

## Upload to GitHub
Double-click `upload_to_github.bat`. First time: create an **empty** repository at https://github.com/new (no README,
.gitignore or licence) and paste its address when asked; Git may open a GitHub sign-in window. Each run uploads the
application only, labelled with the beta version (`Beta N: <your description>`). Never uploaded (`.gitignore`): `data\`
(database, position tracks, exports), any `.echoreplay` / database file, `tests\sample-replays`, `docs\reference`,
`.venv`, `node_modules`, the built website. If one of those is ever about to be uploaded anyway, the script stops
before anything is sent. Needs Git for Windows (https://git-scm.com/download/win).

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
