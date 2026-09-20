@echo off
title StonksAI - Automated DOCX Report Generator
echo =======================================================
echo     StonksAI CSV/Excel to DOCX Report Generator
echo =======================================================
echo.

".\stocks_env\Scripts\python.exe" generate_docx_report.py %*

echo.
echo Process complete! Press any key to exit.
pause > nul
