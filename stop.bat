@echo off
title JobSearchAIAgentByAnish1989 - Stop
cd /d "%~dp0"
echo Stopping JobSearchAIAgentByAnish1989...
docker compose down
echo Stopped. Your data is safe in the data folder.
pause
