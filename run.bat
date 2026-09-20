@echo off
set HIDE_BATCH_SCREENER=true
title StonksAI Launcher
echo ===================================================
echo             Starting StonksAI Server
echo ===================================================
echo.
echo Launching FastAPI backend in a separate console window...
start "StonksAI Server" cmd /k "title StonksAI Server && set HIDE_BATCH_SCREENER=true&& .\stocks_env\Scripts\python.exe -m backend.main"
echo.
echo Waiting 3 seconds for backend server to boot...
timeout /t 3 /nobreak > nul
echo.
echo Opening StonksAI Dashboard in your default browser...
start http://127.0.0.1:8000/
echo.
echo ===================================================
echo  StonksAI is active! 
echo  Keep the server window open while using the app.
echo ===================================================
pause
