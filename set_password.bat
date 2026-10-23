@echo off
title JobSearchAIAgentByAnish1989 - Set password
cd /d "%~dp0"
set /p UNAME=Login name to set the password for (e.g. anish): 
docker compose exec web python manage.py changepassword %UNAME%
pause
