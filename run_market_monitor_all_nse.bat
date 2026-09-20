@echo off
title Stockbee Whole Exchange Market Monitor
color F0
cls
echo ==========================================================
echo Starting Stockbee Market Monitor (Indian NSE Whole Exchange)
echo ==========================================================
python "%~dp0market_monitor_all_nse.py"
echo.
echo Press any key to exit...
pause > nul
