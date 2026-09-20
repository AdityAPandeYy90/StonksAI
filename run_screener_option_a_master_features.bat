@echo off
color F0
title OPTION A MASTER BREAKOUT FEATURE SCREENER (8 AUTHORITATIVE FEATURES)

echo =========================================================================
echo       OPTION A MASTER BREAKOUT FEATURE SCREENER (MINERVINI + QULLAMAGGIE + STOCKBEE)
echo =========================================================================
echo.
echo Scanning all NSE equities using the 8 Master Quantitative Features:
echo VDU + NR7 + Spread Compression + 10 EMA Surfing + Minervini Stage 2 + TI65
echo.

python "d:\stonks\screener_option_a_master_features.py"

echo.
echo =========================================================================
echo  Full Ranked CSV output saved to: outputs\option_a_master_features_watchlist.csv
echo =========================================================================
echo.
pause
