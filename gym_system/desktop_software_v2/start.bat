@echo off
REM ========================================================
REM  Gym Bridge v2 — Launcher
REM  Run this to start the app silently (no console window).
REM  For debugging, run "python main.py" directly instead.
REM ========================================================

cd /d "%~dp0"

REM Use pythonw (no console window) if available, fall back to python
where pythonw >nul 2>nul
if %ERRORLEVEL% == 0 (
    start "" pythonw main.py
) else (
    start "" python main.py
)
