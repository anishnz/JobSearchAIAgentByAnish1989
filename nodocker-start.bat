@echo off
setlocal
title JobSearchAIAgentByAnish1989 - Start (no Docker)
cd /d "%~dp0"

echo ============================================
echo   JobSearchAIAgentByAnish1989 - Start (no Docker)
echo   Uses Python on this laptop. Same data folder as Docker.
echo ============================================
echo.

REM ---- Do not run two copies on the same data
where docker >nul 2>&1
if errorlevel 1 goto no_docker_check
set DRUN=
for /f %%i in ('docker compose ps --status running -q web 2^>nul') do set DRUN=1
if defined DRUN (
  echo The Docker version is running. Double-click docker-stop.bat first.
  pause
  exit /b 1
)
:no_docker_check

REM ---- 1. Find Python
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (python --version >nul 2>&1 && set PY=python)
if not defined PY (
  echo Python 3.11 or newer is not installed.
  echo Install it from python.org (tick "Add python.exe to PATH"), then run this file again.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)

REM ---- 2. Private Python folder (.venv) and packages
if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python folder .venv (first time only)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv.
    pause
    exit /b 1
  )
)
echo Checking packages (the first time takes a few minutes)...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Package install failed. Check your internet and try again.
  pause
  exit /b 1
)

REM ---- 3. First run: create .env
if exist ".env" goto env_ok
copy ".env.example" ".env" >nul
powershell -NoProfile -Command "$k=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N'); (Get-Content '.env') -replace 'change-me-to-a-long-random-string',$k | Set-Content '.env'"
:env_ok

REM ---- 4. Port check FIRST (skip if our own window is already running)
set KEEP=
tasklist /fi "WINDOWTITLE eq JobSearchAI-web*" 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 set KEEP=-KeepIfOurs
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
goto prepare

:port_fail
echo Could not find a free port. Close some programs and try again.
pause
exit /b 1

:prepare
echo Preparing the database...
".venv\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 (
  echo Database step failed. See the messages above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py collectstatic --noinput >nul

REM ---- 5. Start website and daily scheduler in two small windows
tasklist /fi "WINDOWTITLE eq JobSearchAI-web*" 2>nul | findstr /i "cmd.exe" >nul
if errorlevel 1 start "JobSearchAI-web" /min cmd /c ".venv\Scripts\python.exe -m waitress --listen=0.0.0.0:%APP_PORT% config.wsgi:application"
tasklist /fi "WINDOWTITLE eq JobSearchAI-scheduler*" 2>nul | findstr /i "cmd.exe" >nul
if errorlevel 1 start "JobSearchAI-scheduler" /min cmd /c ".venv\Scripts\python.exe manage.py run_scheduler"

echo Waiting for the website...
for /l %%i in (1,1,30) do (
  curl -s -o nul http://localhost:%APP_PORT%/login/ && goto web_ok
  timeout /t 2 /nobreak >nul
)
echo The website is slow to start. Look at the small minimized windows for messages.
pause
exit /b 1

:web_ok
if exist "data\.admin_created" goto open_site
echo.
echo You need an admin login (only once).
choice /c YN /m "Create your admin login now"
if errorlevel 2 goto open_site
".venv\Scripts\python.exe" manage.py createsuperuser
if not errorlevel 1 echo created> "data\.admin_created"

:open_site
start "" http://localhost:%APP_PORT%
echo.
echo ============================================
echo   Running (no Docker) at http://localhost:%APP_PORT%
echo   Personal links on this laptop: http://NAMEcv.localhost:%APP_PORT%
if defined HOST_LAN_IP echo   From phones/laptops at home: http://%HOST_LAN_IP%:%APP_PORT%
echo   Daily job search: 8:00 AM Auckland time (while this laptop is on)
echo   Pause daily search: nodocker-pause.bat    Stop everything: nodocker-stop.bat
echo ============================================
echo.
pause
