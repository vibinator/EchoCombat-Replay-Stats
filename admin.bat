@echo off
rem EchoVR Replay Stats admin console (player merges, challenge period, failed replays). See docs\Setup.MD.
rem No arguments: interactive menu. "admin.bat --help" lists the commands.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to set up the app.
  pause
  exit /b 1
)
".venv\Scripts\python" app\admin_console.py %*
if "%~1"=="" pause
