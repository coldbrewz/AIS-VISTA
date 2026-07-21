@echo off
setlocal enabledelayedexpansion
title VISTA AI Bot Server (Local - GOWS Docker)
echo ==========================================
echo Starting VISTA AI WhatsApp Bot (GOWS)
echo ==========================================

:: Navigate to the project root directory
cd /d "%~dp0"

:: 1. Load Environment Variables from .env
if exist ".env" (
    echo Loading variables from .env...
    for /f "usebackq tokens=1,* eol=# delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
) else (
    echo WARNING: .env file not found!
)

:: 2. Stop any existing WAHA container
echo Stopping old WAHA container (if running)...
docker stop waha_local >nul 2>&1
docker rm waha_local >nul 2>&1

:: 3. Start WAHA GOWS via Docker
echo Starting WAHA GOWS Docker container...
docker compose -f docker-compose.local.yml up -d

:: 4. Wait for WAHA to initialize
echo Waiting 10 seconds for GOWS to initialize...
timeout /t 10

:: 5. Start the Python Server
echo Starting Python Backend...
set WAHA_URL=http://localhost:3000
python main.py

pause
