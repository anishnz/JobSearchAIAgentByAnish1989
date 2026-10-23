@echo off
title JobSearchAIAgentByAnish1989 - Create admin
cd /d "%~dp0"
echo Create an admin login for the dashboard.
docker compose exec web python manage.py createsuperuser
if not errorlevel 1 echo created> "data\.admin_created"
pause
