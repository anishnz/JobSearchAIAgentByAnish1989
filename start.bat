@echo off
setlocal
title JobSearchAIAgentByAnish1989 - Start
cd /d "%~dp0"

echo ============================================
echo   JobSearchAIAgentByAnish1989 - Starting
echo ============================================
echo.

REM ---- 1. Check Docker Desktop is installed
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not installed.
  echo Please install it, restart your laptop, then run this file again.
  start "" https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

REM ---- 2. Make sure Docker Desktop is running
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo Starting Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker (this can take up to 3 minutes)...
for /l %%i in (1,1,60) do (
  docker info >nul 2>&1 && goto docker_ok
  timeout /t 3 /nobreak >nul
)
echo Docker did not start. Please open Docker Desktop yourself, then run this file again.
pause
exit /b 1

:docker_ok
echo Docker is running.

REM ---- 3. First run: create the .env settings file
if exist ".env" goto env_ok
echo.
echo First run: creating your settings file (.env)...
copy ".env.example" ".env" >nul
powershell -NoProfile -Command "$k=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N'); (Get-Content '.env') -replace 'change-me-to-a-long-random-string',$k | Set-Content '.env'"
echo.
echo Notepad will open now. Paste your Claude API key after ANTHROPIC_API_KEY=
echo (You can leave it empty to use the free basic matching.) Save and close Notepad.
notepad ".env"
:env_ok

REM ---- 4. Build and start the containers
echo.
echo Starting the app (the first time can take a few minutes)...
docker compose up -d --build
if errorlevel 1 (
  echo Something went wrong while starting. See the messages above.
  pause
  exit /b 1
)

REM ---- 5. Wait until the website answers
echo Waiting for the website...
for /l %%i in (1,1,40) do (
  curl -s -o nul http://localhost:8000/login/ && goto web_ok
  timeout /t 2 /nobreak >nul
)
echo The website is slow to start. Run logs.bat to see what is happening.
pause
exit /b 1

:web_ok
REM ---- 6. First run: create the admin login
if exist "data\.admin_created" goto open_site
echo.
echo You need an admin login (only once).
choice /c YN /m "Create your admin login now"
if errorlevel 2 goto open_site
docker compose exec web python manage.py createsuperuser
if not errorlevel 1 echo created> "data\.admin_created"

:open_site
start "" http://localhost:8000
echo.
echo ============================================
echo   Running at http://localhost:8000
echo   Daily job search: 8:00 AM Auckland time
echo   To stop: double-click stop.bat
echo ============================================
echo.
pause
