@echo off
title "StonksAI - Stock Fundamental & News Analyzer"
echo ==========================================
echo Starting StonksAI Application...
echo ==========================================

:: Wait 2 seconds, then automatically open browser to local dashboard
start "" cmd /c "timeout /t 2 && start http://127.0.0.1:8000/"

:: Execute backend server blocking command
echo Launching FastAPI Backend Server...
".\stocks_env\Scripts\python.exe" -m backend.main
