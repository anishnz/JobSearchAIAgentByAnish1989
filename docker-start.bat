@echo off
setlocal
title JobSearchAIAgentByAnish1989 - Start (Docker)
cd /d "%~dp0"

echo ============================================
echo   JobSearchAIAgentByAnish1989 - Start (Docker mode)
echo ============================================
echo.

REM ---- Do not run two copies on the same data
tasklist /fi "WINDOWTITLE eq JobSearchAI-web*" 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 (
  echo The no-Docker version is running. Double-click nodocker-stop.bat first.
  pause
  exit /b 1
)

REM ---- 1. Docker Desktop installed?
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not installed.
  echo Install it and restart the laptop, or use nodocker-start.bat instead.
  start "" https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

REM ---- 2. Docker Desktop running?
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo Starting Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker (this can take up to 3 minutes)...
for /l %%i in (1,1,60) do (
  docker info >nul 2>&1 && goto docker_ok
  timeout /t 3 /nobreak >nul
)
echo Docker did not start. Open Docker Desktop yourself, then run this file again.
pause
exit /b 1

:docker_ok
echo Docker is running.

REM ---- 3. First run: create .env
if exist ".env" goto env_ok
echo First run: creating your settings file (.env)...
copy ".env.example" ".env" >nul
powershell -NoProfile -Command "$k=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N'); (Get-Content '.env') -replace 'change-me-to-a-long-random-string',$k | Set-Content '.env'"
echo (Your Claude key is optional. Each person can add their own later in Settings.)
:env_ok

REM ---- 4. Port check FIRST. If our own app is already running, keep its port.
set KEEP=
set RUNNING=
for /f %%i in ('docker compose ps --status running -q web 2^>nul') do set RUNNING=1
if defined RUNNING set KEEP=-KeepIfOurs
set APP_PORT=
set OLD_PORT=
for /f "tokens=1,2" %%a in ('powershell -NoProfile -ExecutionPolicy Bypass -File "docker\pick_port.ps1" %KEEP%') do (
  set APP_PORT=%%a
  set OLD_PORT=%%b
)
if not defined APP_PORT goto port_fail
if "%APP_PORT%"=="0" goto port_fail
if defined OLD_PORT echo Port %OLD_PORT% was busy (maybe your ERP). Using free port %APP_PORT% instead and saved it in .env.
echo Using port %APP_PORT%.
set HOST_LAN_IP=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "docker\lan_ip.ps1"`) do set HOST_LAN_IP=%%i
goto build

:port_fail
echo Could not find a free port. Close some programs and try again.
pause
exit /b 1

:build
echo.
echo Starting the app (the first time can take a few minutes)...
docker compose up -d --build
if errorlevel 1 (
  echo Something went wrong while starting. See the messages above.
  pause
  exit /b 1
)

echo Waiting for the website...
for /l %%i in (1,1,40) do (
  curl -s -o nul http://localhost:%APP_PORT%/login/ && goto web_ok
  timeout /t 2 /nobreak >nul
)
echo The website is slow to start. Run logs.bat to see what is happening.
pause
exit /b 1

:web_ok
if exist "data\.admin_created" goto open_site
echo.
echo You need an admin login (only once).
choice /c YN /m "Create your admin login now"
if errorlevel 2 goto open_site
docker compose exec web python manage.py createsuperuser
if not errorlevel 1 echo created> "data\.admin_created"

:open_site
start "" http://localhost:%APP_PORT%
echo.
echo ============================================
echo   Running (Docker) at http://localhost:%APP_PORT%
echo   Personal links on this laptop: http://NAMEcv.localhost:%APP_PORT%
if defined HOST_LAN_IP echo   From phones/laptops at home: http://%HOST_LAN_IP%:%APP_PORT%
echo   Daily job search: 8:00 AM Auckland time
echo   Pause daily search: docker-pause.bat    Stop everything: docker-stop.bat
echo ============================================
echo.
pause
