@echo off
rem Bounds editor: draw the play-area outline of each map by hand. Prepares the page (where players are, from the
rem latest matches in the data folder; read-only) and opens it in the browser. Save writes echo_bounds.json.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
if exist "settings.local.bat" call "settings.local.bat"
".venv\Scripts\python" app\tools\bounds_editor\make.py %*
