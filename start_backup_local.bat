@echo off
setlocal enabledelayedexpansion
title VISTA AI Bot Server (Local Backup - No Docker)
echo ==========================================
echo Starting VISTA AI WhatsApp Bot (No Docker)
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
    echo WARNING: .env file not found. WAHA might not start properly!
)

:: Ensure WAHA specific native variables are set
if "%WHATSAPP_HOOK_URL%"=="" set WHATSAPP_HOOK_URL=http://localhost:5001/webhook
if "%WHATSAPP_HOOK_EVENTS%"=="" set WHATSAPP_HOOK_EVENTS=message
if "%WHATSAPP_DEFAULT_ENGINE%"=="" set WHATSAPP_DEFAULT_ENGINE=NOWEB
if "%PUPPETEER_EXECUTABLE_PATH%"=="" set PUPPETEER_EXECUTABLE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
if "%WAHA_BROWSER_EXECUTABLE_PATH%"=="" set WAHA_BROWSER_EXECUTABLE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
if "%WHATSAPP_BROWSER_EXECUTABLE_PATH%"=="" set WHATSAPP_BROWSER_EXECUTABLE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
if "%WHATSAPP_BROWSER_ARGS%"=="" set WHATSAPP_BROWSER_ARGS=--no-sandbox,--disable-setuid-sandbox
if "%WAHA_DASHBOARD_USERNAME%"=="" set WAHA_DASHBOARD_USERNAME=admin
if "%WAHA_DASHBOARD_PASSWORD%"=="" set WAHA_DASHBOARD_PASSWORD=admin123
:: CRITICAL FIX: Disable WAHA Apps subsystem. It queries a 'apps' SQLite table
:: that doesn't exist in the CORE version, which causes session.status = FAILED
:: before the WhatsApp engine even gets a chance to start.
set WAHA_APPS_ENABLED=false

:: Swagger variables for WAHA
set WHATSAPP_SWAGGER_USERNAME=%WAHA_DASHBOARD_USERNAME%
set WHATSAPP_SWAGGER_PASSWORD=%WAHA_DASHBOARD_PASSWORD%

:: 2. Start WAHA Server locally in a new window
echo Starting WAHA NodeJS Server from source...
if not exist "waha-core\node_modules" (
    echo Installing WAHA dependencies for the first time. This may take a few minutes...
    cd waha-core
    call npm install --legacy-peer-deps
    cd ..
)
set WHATSAPP_FILES_FOLDER=%~dp0waha-core\.media
start "WAHA Server (Native)" cmd /c "cd waha-core && npx ts-node -T -r tsconfig-paths/register src/main.ts"

:: 3. Wait 15 seconds for NestJS to compile and WAHA to start
echo Waiting 15 seconds for WAHA to initialize...
timeout /t 15

:: 4. Start the Python Server
echo Starting Python Backend...
set WAHA_URL=http://localhost:3000
python main.py

pause
