@echo off
title JobSearchAIAgentByAnish1989 - Search now
cd /d "%~dp0"
echo Running the job search now for every active user...
docker compose exec web python manage.py run_daily_search
echo Done. Open the dashboard to see the results.
pause
