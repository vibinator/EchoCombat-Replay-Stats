@echo off
rem Upload the application to GitHub - no replay data. What stays local is listed in .gitignore
rem (data\, *.echoreplay, the database, tests\sample-replays, docs\reference, .venv, node_modules, build output).
rem First run: asks for the GitHub repository URL (create an EMPTY repository first at https://github.com/new).
setlocal EnableDelayedExpansion
cd /d "%~dp0"
rem Git shows a list longer than the window in its viewer ("less"), which waits for q: the upload seemed to stop at
rem the list of changes (user, 2026-11-01). Never use the viewer here.
set "GIT_PAGER=cat"

where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Get it from https://git-scm.com/download/win and run this again.
  goto :fail
)
if not exist ".gitignore" (
  echo .gitignore is missing: without it replay data could be uploaded. Stopping.
  goto :fail
)

rem --- first run: local repository, GitHub address, commit identity -------------------------------
if not exist ".git" (
  echo [setup] Creating the local Git repository...
  git init -q -b main
  if errorlevel 1 goto :error
)
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo.
  echo  First upload. Create an EMPTY repository on https://github.com/new
  echo  ^(no README, .gitignore or licence^), then paste its address here.
  echo.
  set "REPO="
  set /p "REPO=GitHub repository URL (e.g. https://github.com/you/EchoVR-Replay-Stats.git): "
  if "!REPO!"=="" goto :fail
  git remote add origin "!REPO!"
  if errorlevel 1 goto :error
)
git config user.name >nul 2>nul
if errorlevel 1 (
  set /p "GIT_NAME=Your name for the upload history: "
  git config user.name "!GIT_NAME!"
)
git config user.email >nul 2>nul
if errorlevel 1 (
  echo Tip: GitHub's private address works, e.g. 12345+you@users.noreply.github.com
  set /p "GIT_EMAIL=Your email for the upload history: "
  git config user.email "!GIT_EMAIL!"
)

rem --- stage the application ---------------------------------------------------------------------
git add -A
if errorlevel 1 goto :error

rem Safety net: never upload data, even if .gitignore was edited (git's own path matching; findstr is unreliable
rem with several patterns).
set "BLOCKED=%TEMP%\echovr-blocked.txt"
git -c core.quotepath=off diff --cached --name-only -- "*.echoreplay" "*.ecrreplay" "*.db" "*.db-wal" "*.db-shm" "*.sqlite" "*tracks.bin" "data/*" "tests/sample-replays/*" "docs/reference/*" "*node_modules/*" ".venv/*" > "%BLOCKED%"
set "BLOCKED_SIZE=0"
for %%F in ("%BLOCKED%") do set "BLOCKED_SIZE=%%~zF"
if not "!BLOCKED_SIZE!"=="0" (
  echo.
  echo  STOPPED: these files are replay data or generated files and must not be uploaded:
  type "%BLOCKED%"
  git reset -q
  echo  Nothing was uploaded. Check .gitignore.
  goto :fail
)

rem The replay share's network address stays out of the repository (user, 2026-10-30).
git grep --cached -I -l -E "192\.168\.[0-9]+\.[0-9]+" > "%BLOCKED%" 2>nul
set "BLOCKED_SIZE=0"
for %%F in ("%BLOCKED%") do set "BLOCKED_SIZE=%%~zF"
if not "!BLOCKED_SIZE!"=="0" (
  echo.
  echo  STOPPED: these files contain a local network address ^(replace it with a placeholder^):
  type "%BLOCKED%"
  git reset -q
  echo  Nothing was uploaded.
  goto :fail
)

rem GitHub, Cloudflare tunnel and Discord tokens / secrets (e.g. pasted into docker-compose.yml for the NAS) never go to GitHub.
git grep --cached -I -l -E "ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|eyJhIjoi[A-Za-z0-9+/=]{20,}|[MN][A-Za-z0-9_-]{23,27}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}|ECHOVR_DISCORD_CLIENT_SECRET: *([A-XZa-z0-9_-]|Y[A-NP-Za-z0-9_-])[A-Za-z0-9_-]{18,}" > "%BLOCKED%" 2>nul
set "BLOCKED_SIZE=0"
for %%F in ("%BLOCKED%") do set "BLOCKED_SIZE=%%~zF"
if not "!BLOCKED_SIZE!"=="0" (
  echo.
  echo  STOPPED: these files contain a GitHub, Cloudflare or Discord token ^(put the YOUR_... placeholder back^):
  type "%BLOCKED%"
  git reset -q
  echo  Nothing was uploaded.
  goto :fail
)

rem --- commit, labelled with the beta version (app\backend\version.py) ----------------------------
set "BETA=?"
for /f "tokens=3" %%v in ('findstr /B /C:"BETA = " app\backend\version.py') do set "BETA=%%v"

git diff --cached --quiet
if errorlevel 1 (
  echo.
  echo  Changes in this upload:
  git diff --cached --stat
  echo.
  set "MSG="
  set /p "MSG=Short description of this update (Enter = just "Beta !BETA!"): "
  if "!MSG!"=="" (set "MSG=Beta !BETA!") else (set "MSG=Beta !BETA!: !MSG!")
  git commit -q -m "!MSG!"
  if errorlevel 1 goto :error
) else (
  echo No changes since the last upload.
)

rem --- push --------------------------------------------------------------------------------------
echo.
echo Uploading to GitHub ^(the first time, a GitHub sign-in window may open^)...
git push -u origin main
if errorlevel 1 goto :error
echo.
echo Done: Beta !BETA! is on GitHub.
pause
exit /b 0

:error
echo.
echo Something went wrong - see the message above. Nothing secret or raw was uploaded.
:fail
pause
exit /b 1
