@echo off
title JobSearchAIAgentByAnish1989 - Stop (no Docker)
cd /d "%~dp0"
echo Stopping the no-Docker version...
taskkill /fi "WINDOWTITLE eq JobSearchAI-web*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq JobSearchAI-scheduler*" /t /f >nul 2>&1
REM Safety: also close whatever still listens on our port
set APP_PORT=8010
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"APP_PORT=" ".env" 2^>nul') do set APP_PORT=%%b
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%APP_PORT% .*LISTENING"') do taskkill /pid %%p /t /f >nul 2>&1
echo Stopped. Your data is safe in the data folder.
pause
