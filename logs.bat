@echo off
title JobSearchAIAgentByAnish1989 - Logs
cd /d "%~dp0"
echo Showing live logs. Press Ctrl+C to close.
docker compose logs -f --tail 100
