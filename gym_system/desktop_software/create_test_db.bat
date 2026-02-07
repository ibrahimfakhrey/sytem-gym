@echo off
echo ============================================================
echo   Creating Test Database for Gym Management System
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Install required packages
echo Installing required packages...
pip install pyodbc pywin32 >nul 2>&1

REM Run the script
echo.
echo Running database creation script...
echo.
python "%~dp0create_test_database.py"

echo.
pause
