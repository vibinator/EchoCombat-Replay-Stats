@echo off
rem Start the site locally for end-to-end testing with the Discord login bypassed (docs/reference/E2E-TESTING.md).
rem   run_local.bat                 data\ (the normal local database), replay source from settings.local.bat
rem   run_local.bat --data <dir>    a separate data folder (empty = re-import from the share)
rem Fake Discord secrets switch the login on; the 18-digit test id in ECHOVR_DISCORD_PREVIEW_ROLES gets the Console.
rem Rate limiting is off so the sweeps do not hit 429. Never use these values on the NAS.
setlocal
cd /d "%~dp0..\..\.."
if exist "settings.local.bat" call "settings.local.bat"
if "%~1"=="--data" set ECHOVR_DATA_DIR=%~2
set ECHOVR_DISCORD_CLIENT_SECRET=local-e2e-secret
set ECHOVR_DISCORD_BOT_TOKEN=local-e2e-token
set ECHOVR_DISCORD_PREVIEW_ROLES=100000000000000001
set ECHOVR_PUBLIC_URL=http://127.0.0.1:8000
set ECHOVR_RATE_LIMIT_PER_MIN=0
set ECHOVR_RATE_LIMIT_PER_HOUR=0
if not defined ECHOVR_WORKERS set ECHOVR_WORKERS=4
echo Local e2e server: http://127.0.0.1:8000  data=%ECHOVR_DATA_DIR%  source=%ECHOVR_REPLAY_SOURCE%
echo Cookie: .venv\Scripts\python app\tools\e2e\local_login.py
".venv\Scripts\python" -m uvicorn backend.main:app --app-dir app --host 127.0.0.1 --port 8000
