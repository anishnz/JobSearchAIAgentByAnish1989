@echo off
title JobSearchAIAgentByAnish1989 - Resume daily search (Docker)
cd /d "%~dp0"
docker compose start scheduler
echo Daily search is running again (8:00 AM Auckland time).
pause
