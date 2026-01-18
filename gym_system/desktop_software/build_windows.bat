@echo off
echo ========================================
echo   Gym Management System - Build Script
echo   نظام إدارة الجيم - سكربت البناء
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed!
    echo Please install Python 3.9+ from python.org
    pause
    exit /b 1
)

:: Install requirements
echo [1/4] Installing dependencies...
echo      تثبيت المتطلبات...
pip install -r requirements.txt pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo      Done!
echo.

:: Check for icon
if not exist "assets\icon.ico" (
    echo [WARNING] No icon.ico found in assets folder
    echo          Creating placeholder...
    mkdir assets 2>nul
    echo. > assets\icon.ico
)

:: Build EXE
echo [2/4] Building executable...
echo      إنشاء الملف التنفيذي...
pyinstaller GymSystem.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] Failed to build executable
    pause
    exit /b 1
)
echo      Done!
echo.

:: Check if Inno Setup is installed
set INNO_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %INNO_PATH% (
    set INNO_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if exist %INNO_PATH% (
    echo [3/4] Building installer...
    echo      إنشاء ملف التثبيت...
    mkdir dist\installer 2>nul
    %INNO_PATH% installer\setup.iss
    if errorlevel 1 (
        echo [ERROR] Failed to build installer
        pause
        exit /b 1
    )
    echo      Done!
    echo.

    echo [4/4] Build complete!
    echo.
    echo ========================================
    echo   Build Output:
    echo   - EXE: dist\GymSystem.exe
    echo   - Installer: dist\installer\GymSystem_Setup_1.0.0.exe
    echo ========================================
) else (
    echo [3/4] Skipping installer (Inno Setup not found)
    echo      To create installer, install Inno Setup from:
    echo      https://jrsoftware.org/isdl.php
    echo.

    echo [4/4] Build complete!
    echo.
    echo ========================================
    echo   Build Output:
    echo   - EXE: dist\GymSystem.exe
    echo ========================================
)

echo.
echo Press any key to exit...
pause >nul
