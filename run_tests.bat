@echo off
title JobSearchAIAgentByAnish1989 - Tests
cd /d "%~dp0"
docker compose exec web python manage.py test tests
pause
