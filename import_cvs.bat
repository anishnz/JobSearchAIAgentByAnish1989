@echo off
title JobSearchAIAgentByAnish1989 - Import CVs
cd /d "%~dp0"
echo Imports CV files from data\import\LOGIN-NAME\ into that person's account.
echo (Example: data\import\sarutuitui\ for Saru.) Duplicates are skipped.
echo.
docker compose exec web python manage.py import_cv_folders
echo.
pause
