@echo off
title JobSearchAIAgentByAnish1989 - Backup
cd /d "%~dp0"
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%t
if not exist "data" (
  echo No data folder yet. Nothing to back up.
  pause
  exit /b 0
)
robocopy "data" "backups\data_%STAMP%" /E /NFL /NDL /NJH /NJS >nul
if %errorlevel% GEQ 8 (echo Backup failed.) else (echo Backup saved to backups\data_%STAMP%)
pause
