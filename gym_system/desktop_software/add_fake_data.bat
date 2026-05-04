@echo off
chcp 65001 >nul
echo ========================================
echo   Adding 50 Fake Members to Database
echo ========================================
echo.

cd /d "%~dp0"

python add_test_data.py

echo.
pause
