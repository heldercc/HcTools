@echo off
REM ============================================================
REM  run.bat  --  one-click launcher for the git-bundle backup tool.
REM  Backs up the git repository of the CURRENT folder, handling the
REM  PowerShell execution policy for you (no setup needed).
REM
REM  Two ways to use it:
REM    1) From a terminal, inside the repo you want to back up:
REM         C:\GitHub\HcTools\git-bundle-tool-bckp\run.bat
REM    2) Copy this file into any repo folder and DOUBLE-CLICK it
REM       (it backs up the repo that folder belongs to).
REM ============================================================
setlocal
set "SCRIPT=%~dp0backup-repo.ps1"
if not exist "%SCRIPT%" set "SCRIPT=C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
echo.
pause
