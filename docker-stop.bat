@echo off
title JobSearchAIAgentByAnish1989 - Stop (Docker)
cd /d "%~dp0"
echo Stopping the Docker version...
docker compose down
echo Stopped. Your data is safe in the data folder.
pause
