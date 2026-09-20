@echo off
title Indian Momentum Screener Launcher
cd /d "%~dp0"

echo ===================================================
echo             Starting Momentum Screener
echo ===================================================
echo.

set PYTHON_EXE=..\stocks_env\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment Python not found at "%PYTHON_EXE%".
    echo Attempting fallback to system 'python'...
    set PYTHON_EXE=python
)

echo Running Python main.py using %PYTHON_EXE%...
"%PYTHON_EXE%" main.py

if %errorlevel% neq 0 (
    echo.
    echo ===================================================
    echo      [ERROR] Momentum Screener Failed! (Code: %errorlevel%)
    echo ===================================================
    pause
    exit /b %errorlevel%
)

echo.
echo ===================================================
echo              Screener Run Finished!
echo ===================================================
pause
