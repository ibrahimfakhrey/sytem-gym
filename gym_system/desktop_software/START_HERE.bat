@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Gym System

REM ============================================================
REM   Gym System - one-click setup and launcher
REM   First run: installs Python (if missing), creates venv,
REM              installs dependencies, creates a Desktop
REM              shortcut, then launches the app.
REM   Repeat runs: just launches the app (fast).
REM   Safe to double-click any time.
REM ============================================================

pushd "%~dp0"
set "APP_DIR=%CD%"
set "VENV_DIR=%APP_DIR%\venv"
set "PY_SETUP=%TEMP%\gym-python-setup.exe"
set "PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Gym System.lnk"

echo ============================================================
echo   Gym System
echo ============================================================
echo.

REM ---- 1. Find Python (or install it) ----------------------------
set "PYTHON="
where py >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)

if not defined PYTHON (
    echo [setup] Python not found. Installing Python 3.12...
    echo.

    where winget >nul 2>&1
    if !errorlevel! == 0 (
        echo [setup] Installing via winget...
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
    ) else (
        echo [setup] Downloading Python installer...
        powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; (New-Object Net.WebClient).DownloadFile('%PY_URL%','%PY_SETUP%')"
        if not exist "%PY_SETUP%" (
            echo.
            echo [error] Could not download Python automatically.
            echo         Please install Python 3.12 manually from:
            echo         https://www.python.org/downloads/
            echo         Then run this file again.
            pause
            exit /b 1
        )
        echo [setup] Running silent installer (per-user)...
        "%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 SimpleInstall=1
        del "%PY_SETUP%" >nul 2>&1
    )

    REM Refresh PATH from the registry so the new py launcher is visible to this session.
    for /f "skip=2 tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "MACHINE_PATH=%%B"
    for /f "skip=2 tokens=2,*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%B"
    set "PATH=!MACHINE_PATH!;!USER_PATH!;%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"

    where py >nul 2>&1 && set "PYTHON=py -3"
    if not defined PYTHON (
        where python >nul 2>&1 && set "PYTHON=python"
    )

    if not defined PYTHON (
        echo.
        echo [error] Python install completed but the launcher is not on PATH.
        echo         Please reboot and run this file again.
        pause
        exit /b 1
    )
)

echo [ok] Python: !PYTHON!

REM ---- 2. Virtual environment ------------------------------------
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    !PYTHON! -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [error] Could not create virtual environment.
        pause
        exit /b 1
    )
)

REM ---- 3. Install / upgrade dependencies (idempotent, quiet) -----
echo [setup] Checking dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%APP_DIR%\requirements.txt" --quiet --disable-pip-version-check
if !errorlevel! neq 0 (
    echo [warn] Some dependencies may have failed to install.
    echo        If the app does not start, run this file again with internet on.
)

REM ---- 4. Verify Microsoft Access ODBC driver --------------------
"%VENV_DIR%\Scripts\python.exe" -c "import pyodbc,sys; sys.exit(0 if any('Access Driver' in d for d in pyodbc.drivers()) else 1)" 2>nul
if !errorlevel! neq 0 (
    echo.
    echo [warn] Microsoft Access ODBC Driver not found.
    echo        The app needs it to read the fingerprint .mdb file.
    echo        Install "Microsoft Access Database Engine 2016 Redistributable":
    echo        https://www.microsoft.com/en-us/download/details.aspx?id=54920
    echo        Pick the x64 version (matches the Python we installed).
    echo.
    echo Press any key to continue anyway...
    pause >nul
)

REM ---- 4b. Database setup (idempotent: try known passwords, else strip) ---
echo.
"%VENV_DIR%\Scripts\python.exe" "%APP_DIR%\setup_databases.py"

REM ---- 5. Create Desktop shortcut on first setup -----------------
if not exist "%SHORTCUT%" (
    echo [setup] Creating Desktop shortcut...
    powershell -NoProfile -Command "$s = New-Object -ComObject WScript.Shell; $sc = $s.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%APP_DIR%\START_HERE.bat'; $sc.WorkingDirectory = '%APP_DIR%'; $sc.Description = 'Gym System'; if (Test-Path '%APP_DIR%\assets\icon.ico') { $sc.IconLocation = '%APP_DIR%\assets\icon.ico' }; $sc.Save()" >nul 2>&1
)

REM ---- 6. Launch -------------------------------------------------
echo.
echo [run] Launching Gym System...
echo.
"%VENV_DIR%\Scripts\python.exe" "%APP_DIR%\main.py"
set "RC=!errorlevel!"

if !RC! neq 0 (
    echo.
    echo [error] App exited with code !RC!. The window will stay open.
    pause
)

popd
endlocal & exit /b %RC%
