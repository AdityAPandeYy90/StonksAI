@echo off
color 0A
title NSE TOMORROW BREAKOUT SCREENER (QULLAMAGGIE 12-POINT CHECKLIST)

echo =========================================================================
echo       NSE TOMORROW BREAKOUT SCREENER (QULLAMAGGIE 12-POINT CHECKLIST)
echo =========================================================================
echo.
echo Scanning NSE Indian Equities for Tomorrow's Opening Range Breakouts...
echo.

.\stocks_env\Scripts\python.exe "d:\stonks\nse_tomorrow_breakout_screener.py"

echo.
echo =========================================================================
echo  Screener Complete! Check nse_tomorrow_breakout_candidates.csv for details.
echo =========================================================================
echo.
pause
