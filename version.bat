@echo off
rem Switch between versions in one step (no data is touched; achievements are computed on request, nothing is stored).
rem   version.bat beta-45   go back to Beta 45 (the version before the medal ladders)
rem   version.bat latest    come back to the newest version
rem   version.bat           list the versions you can go to
rem Then start the site as usual with run.bat (it rebuilds the website for the version you are on).
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Versions you can go to ^(newest last^):
  git tag --sort=creatordate
  echo   latest
  echo You are on:
  git describe --tags --always
  goto :eof
)
git diff --quiet HEAD -- . 2>nul
if errorlevel 1 (
  echo There are changes that are not saved in a version. Stopping so nothing is lost.
  exit /b 1
)
if /i "%~1"=="latest" (git checkout main) else (git checkout "%~1")
if errorlevel 1 (echo Could not switch. & exit /b 1)
echo Now on: & git describe --tags --always
echo Stop the site if it is running, then start run.bat again.
