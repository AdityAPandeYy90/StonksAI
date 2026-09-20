@echo off
title Indian Relative Strength Screener Launcher
cd /d "%~dp0"

echo ===================================================
echo             Starting Relative Strength Screener
echo ===================================================
echo.

set PYTHON_EXE=..\stocks_env\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment Python not found at "%PYTHON_EXE%".
    echo Attempting fallback to system 'python'...
    set PYTHON_EXE=python
)

echo Running Python rs_screener.py using %PYTHON_EXE%...
"%PYTHON_EXE%" rs_screener.py

if %errorlevel% neq 0 (
    echo.
    echo ===================================================
    echo   [ERROR] RS Screener Failed! (Code: %errorlevel%)
    echo ===================================================
    pause
    exit /b %errorlevel%
)

echo.
echo ===================================================
echo           Relative Strength Screener Run Finished!
echo ===================================================
pause
