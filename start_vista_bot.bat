@echo off
title VISTA AI Bot Server
echo ==========================================
echo Starting VISTA AI WhatsApp Bot...
echo ==========================================

:: Navigate to the bot directory
cd /d "C:\Users\admin.DESKTOP-0RB5H2T.000\Documents\AIS-VISTA"

:: Start WAHA Docker container first
echo Starting WAHA Docker Container...
docker compose up -d

:: Start the Python server
python main.py

pause
