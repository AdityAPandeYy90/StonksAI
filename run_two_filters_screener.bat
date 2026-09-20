@echo off
title Two Filters Momentum Screener
color 0A
echo =======================================================================
echo            TWO FILTERS MOMENTUM SCREENER (PRIOR MOVE + RS)
echo =======================================================================
echo.
echo  Fetching live data from Yahoo Finance...
echo  Screening stocks against Nifty 500 Benchmark...
echo.

python "%~dp0two_filters_screener.py"

echo.
echo =======================================================================
echo  Screening completed successfully!
echo  CSV and Excel reports have been saved with current Date and Time.
echo =======================================================================
echo.
pause
