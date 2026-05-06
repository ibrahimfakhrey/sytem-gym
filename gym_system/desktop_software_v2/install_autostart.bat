@echo off
REM ========================================================
REM  Gym Bridge v2 — Auto-start Installer
REM  Creates a shortcut in the Windows Startup folder so the
REM  app launches automatically when this user logs in.
REM ========================================================

setlocal

set "SOURCE=%~dp0start.bat"
set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Gym Bridge.lnk"

if not exist "%SOURCE%" (
    echo [ERROR] start.bat not found at "%SOURCE%"
    pause
    exit /b 1
)

REM Create the Startup shortcut using PowerShell
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%TARGET%'); $s.TargetPath = '%SOURCE%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Description = 'Gym Bridge v2 — auto-launches on login'; $s.Save()"

if exist "%TARGET%" (
    echo.
    echo ============================================================
    echo  Auto-start INSTALLED.
    echo ============================================================
    echo.
    echo  The app will launch automatically on next Windows login.
    echo.
    echo  Shortcut location:
    echo    %TARGET%
    echo.
    echo  To remove: run uninstall_autostart.bat
    echo.
) else (
    echo [ERROR] Failed to create startup shortcut
)

endlocal
pause
