@echo off
echo ==========================================================
echo Starting Stockbee Market Monitor (Indian NSE Nifty 500)
echo ==========================================================
python "%~dp0market_monitor.py"
echo.
echo Press any key to exit...
pause > nul
