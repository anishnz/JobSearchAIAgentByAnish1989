@echo off
title JobSearchAIAgentByAnish1989 - Pause daily search (Docker)
cd /d "%~dp0"
docker compose stop scheduler
echo Daily search is PAUSED. The website stays open so you can still use it.
echo To start the daily search again, double-click docker-resume.bat
pause
