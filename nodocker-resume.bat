@echo off
title JobSearchAIAgentByAnish1989 - Resume daily search (no Docker)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run nodocker-start.bat first.
  pause
  exit /b 1
)
tasklist /fi "WINDOWTITLE eq JobSearchAI-scheduler*" 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 (
  echo The daily search is already running.
  pause
  exit /b 0
)
start "JobSearchAI-scheduler" /min cmd /c ".venv\Scripts\python.exe manage.py run_scheduler"
echo Daily search is running again (8:00 AM Auckland time).
pause
