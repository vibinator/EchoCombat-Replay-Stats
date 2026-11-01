@echo off
rem Is Cloudflare caching the public site as intended? Asks the site a few questions; changes nothing.
rem   check_cloudflare.bat                          checks https://echocombat.com
rem   check_cloudflare.bat https://other.example    checks another address
rem See docs\Setup.MD, "Cloudflare cache".
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
".venv\Scripts\python" app\cloudflare_check.py %*
if "%~1"=="" pause
