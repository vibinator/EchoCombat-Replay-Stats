@echo off
rem Read replays for the website on THIS PC instead of on the NAS. See docs\Setup.MD, "Remote processing".
rem Turn it on first: Console > "Process replays on another PC" (or: admin.bat remote --on). Ctrl+C stops it.
rem Needs settings.local.bat (never uploaded) with:
rem   set ECHOVR_REMOTE_WORKER_SECRET=the same value as on the NAS
rem   set ECHOVR_REMOTE_SERVER=https://echocombat.com        (or http://<nas address>:8000 on the home network)
rem   set ECHOVR_REPLAY_SOURCE=e:\ECRanked\Replays           (the replay share as this PC sees it)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
if exist "settings.local.bat" call "settings.local.bat"
rem This PC must run the same version as the website: update first (git pull), then run.bat once.
".venv\Scripts\python" app\remote_worker.py %*
pause
