@echo off
REM ========================================================
REM  Gym Bridge v2 — Auto-start Uninstaller
REM  Removes the Startup shortcut so the app no longer
REM  launches automatically on login.
REM ========================================================

setlocal

set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Gym Bridge.lnk"

if exist "%TARGET%" (
    del "%TARGET%"
    echo.
    echo ============================================================
    echo  Auto-start REMOVED.
    echo ============================================================
    echo.
    echo  The app will no longer launch automatically on login.
    echo  You can still run it manually with start.bat
    echo.
) else (
    echo.
    echo  Auto-start was not installed (nothing to remove).
    echo.
)

endlocal
pause
