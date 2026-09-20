@echo off
color F0
title OPTION A BREAKOUT TOMORROW PREDICTOR (VDU + NR7 + VOLATILITY CONTRACTION)

echo =========================================================================
echo       OPTION A BREAKOUT TOMORROW PREDICTOR (STEP 1 WATCHLIST RANKER)
echo =========================================================================
echo.
echo Scanning all NSE equities for Volume Dry Up (VDU), NR7 Range Compression,
echo and 10 EMA proximity to find the highest probability breakout candidates...
echo.

python "d:\stonks\screener_option_a_breakout_predictor.py"

echo.
echo =========================================================================
echo  Full Ranked CSV output saved to: outputs\breakout_tomorrow_predictor.csv
echo =========================================================================
echo.
pause
