@echo off
rem Build the 3D tracks of every processed replay that lacks them (3D player / Compare heatmaps). Slow, safe to stop and rerun.
rem   backfill_tracks3d.bat --dry-run      count what is missing
rem   backfill_tracks3d.bat --workers 6    build with 6 processes (default: half the cores)
rem   backfill_tracks3d.bat --heights      only write the small heights.bin files 3D player heatmaps read (minutes, no replay is read)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
if exist "settings.local.bat" call "settings.local.bat"
".venv\Scripts\python" app\tools\backfill_tracks3d.py %*
