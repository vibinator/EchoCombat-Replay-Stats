@echo off
rem Start Echo Combat Stats locally: sets up on first run, builds the site, opens the browser.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating Python environment...
  python -m venv .venv
  if errorlevel 1 goto :error
  ".venv\Scripts\python" -m pip install -r app\backend\requirements.txt
  if errorlevel 1 goto :error
)
rem New packages after an update (quick when nothing is missing)
".venv\Scripts\python" -m pip install -q --disable-pip-version-check -r app\backend\requirements.txt
if errorlevel 1 goto :error

cd app\frontend
if not exist "node_modules" (
  echo [setup] Installing frontend packages...
  call npm install
  if errorlevel 1 goto :error
)
echo [build] Building website...
call npm run build
if errorlevel 1 goto :error
cd /d "%~dp0"

echo.
echo  Echo Combat Stats is running at http://127.0.0.1:8000
echo  Close this window or press Ctrl+C to stop.
echo.
rem Private settings (Discord secret / bot token): settings.local.bat, never uploaded. See Setup.MD, Discord login.
if exist "settings.local.bat" call "settings.local.bat"
if not defined NO_BROWSER start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
".venv\Scripts\python" -m uvicorn backend.main:app --app-dir app --host 127.0.0.1 --port 8000
goto :eof

:error
echo.
echo Setup or build failed - see docs\Setup.MD (Troubleshooting).
pause
exit /b 1
