@echo off
title JobSearchAIAgentByAnish1989 - Pause daily search (no Docker)
cd /d "%~dp0"
taskkill /fi "WINDOWTITLE eq JobSearchAI-scheduler*" /t /f >nul 2>&1
echo Daily search is PAUSED. The website stays open so you can still use it.
echo To start the daily search again, double-click nodocker-resume.bat
pause
