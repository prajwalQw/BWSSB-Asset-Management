@echo off
title Bengaluru Water Network Digital Twin
echo ======================================================================
echo    BENGALURU WATER NETWORK DIGITAL TWIN — BWSSB OPERATIONS
echo ======================================================================
echo.
echo Activating Virtual Environment and Starting Services...
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not detected!
    echo Creating venv and installing pinned requirements...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

.venv\Scripts\python.exe run_app.py
pause
