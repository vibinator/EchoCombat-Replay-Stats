@echo off
rem Echo Combat Stats admin console (player merges, challenge period, failed replays). See docs\Setup.MD.
rem No arguments: interactive menu. "admin.bat --help" lists the commands.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
rem Discord bot token for listing server roles (option 14): the same private settings.local.bat as run.bat
if exist "settings.local.bat" call "settings.local.bat"
".venv\Scripts\python" app\admin_console.py %*
if "%~1"=="" pause
