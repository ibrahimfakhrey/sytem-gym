@echo off
setlocal enabledelayedexpansion
title Gym Fingerprint Bridge - Setup & Run
color 0A

echo.
echo ============================================
echo    GYM FINGERPRINT BRIDGE SERVICE
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python is installed
    goto :install_packages
)

echo [!] Python not found. Installing automatically...
echo.

REM Create temp folder for download
if not exist "%TEMP%\gym_setup" mkdir "%TEMP%\gym_setup"

REM Download Python installer using PowerShell
echo [1/4] Downloading Python installer...
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\gym_setup\python_installer.exe'}"

if not exist "%TEMP%\gym_setup\python_installer.exe" (
    echo [ERROR] Failed to download Python installer
    echo Please download Python manually from https://python.org
    pause
    exit /b 1
)

echo [2/4] Installing Python (this may take a minute)...
REM Install Python silently with PATH option
"%TEMP%\gym_setup\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1

REM Wait for installation to complete
timeout /t 10 /nobreak >nul

REM Refresh environment variables
echo [3/4] Refreshing environment...
call refreshenv >nul 2>&1

REM Try to find Python in common locations
set "PYTHON_PATH="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
)
if exist "C:\Python311\python.exe" (
    set "PYTHON_PATH=C:\Python311\python.exe"
)

REM Check if Python works now
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python installed successfully!
    goto :install_packages
)

REM Try with explicit path
if defined PYTHON_PATH (
    echo [OK] Python found at: %PYTHON_PATH%
    set "PYTHON_CMD=%PYTHON_PATH%"
    goto :install_packages_explicit
)

echo.
echo [!] Python installed but needs restart.
echo     Please RESTART your computer and run this again.
echo.
pause
exit /b 0

:install_packages
set "PYTHON_CMD=python"

:install_packages_explicit
echo [4/4] Installing required packages...
%PYTHON_CMD% -m pip install --upgrade pip --quiet 2>nul
%PYTHON_CMD% -m pip install requests --quiet

echo.
echo ============================================
echo    STARTING BRIDGE SERVICE
echo ============================================
echo.
echo Cloud: https://gymsystem.pythonanywhere.com
echo Press Ctrl+C to stop
echo.

REM Change to script directory and run bridge
cd /d "%~dp0"
%PYTHON_CMD% gym_bridge.py

pause
