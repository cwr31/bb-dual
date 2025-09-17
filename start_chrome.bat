@echo off
setlocal enabledelayedexpansion

echo.
echo ==========================================
echo Chrome Browser Launcher for BybitBot
echo ==========================================

set "USER_DATA_DIR=C:\Users\wenrui.cao\AppData\Local\BybitBot"

if not exist "%USER_DATA_DIR%" (
    echo Creating user data directory...
    mkdir "%USER_DATA_DIR%" 2>nul
    if !errorlevel! equ 0 (
        echo Directory created: %USER_DATA_DIR%
    ) else (
        echo Failed to create directory
        pause
        exit /b 1
    )
) else (
    echo Directory exists: %USER_DATA_DIR%
)

echo Finding Chrome browser...

set "CHROME_PATH="

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if "%CHROME_PATH%"=="" (
    echo Chrome browser not found!
    echo Please install Google Chrome browser.
    echo.
    pause
    exit /b 1
)

echo Chrome found: %CHROME_PATH%
echo Starting Chrome browser...

start "" "%CHROME_PATH%" --user-data-dir="%USER_DATA_DIR%" --no-first-run --disable-default-apps --start-maximized

timeout /t 2 >nul

echo.
echo Chrome launched successfully!
echo User data will be saved in: %USER_DATA_DIR%
echo You can close this window now.
echo.
pause
