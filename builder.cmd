@echo off
setlocal EnableDelayedExpansion
cls
title PyCord Builder

:: ============================================
:: Restart as administrator
:: ============================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator rights are required...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ============================================
echo          PyCord EXE Builder
echo ============================================
echo.

:: ============================================
:: 0. Remove pathlib backport (fix!)
:: ============================================
echo Checking for incompatible pathlib package...
python -m pip show pathlib >nul 2>&1
if %errorlevel% equ 0 (
    echo    Removing outdated pathlib package...
    python -m pip uninstall -y pathlib >nul 2>&1
    echo    [OK] pathlib removed.
) else (
    echo    [OK] No conflict.
)
echo.

:: ============================================
:: 1. Check PyCord.py
:: ============================================
if not exist "PyCord.py" (
    echo ERROR: PyCord.py was not found!
    echo Expected at: %cd%\PyCord.py
    echo.
    pause
    exit /b 1
)
echo [OK] PyCord.py found.
echo.

:: ============================================
:: 2. Prompt for bot token
:: ============================================
:ask_token
set "TOKEN="
set /p "TOKEN=Discord Bot Token: "
if "!TOKEN!"=="" (
    echo    ERROR: Token must not be empty!
    goto :ask_token
)

:: ============================================
:: 3. Prompt for server ID
:: ============================================
:ask_server
set "SERVER="
set /p "SERVER=Server ID (Guild ID): "
if "!SERVER!"=="" (
    echo    ERROR: Server ID must not be empty!
    goto :ask_server
)

:: ============================================
:: 4. Write Data.txt
:: ============================================
echo.
echo Writing Data.txt ...
(
    echo Token=!TOKEN!
    echo Server=!SERVER!
) > "Data.txt"

if not exist "Data.txt" (
    echo ERROR: Data.txt could not be created!
    pause
    exit /b 1
)
echo [OK] Data.txt created.
echo.

:: ============================================
:: 5. Logo (optional)
:: ============================================
set "LOGO="
set /p "LOGO=Logo path (optional, press Enter to skip): "

if not "!LOGO!"=="" (
    if not exist "!LOGO!" (
        echo    WARNING: Logo not found, ignoring it.
        set "LOGO="
    ) else (
        echo    [OK] Logo will be used as icon: !LOGO!
    )
)
echo.

:: ============================================
:: 6. Target: Desktop (directly, no subfolder)
:: ============================================
set "OUTDIR=%USERPROFILE%\Desktop"
echo    Output goes directly to the Desktop: !OUTDIR!
echo.

:: ============================================
:: 7. Confirmation
:: ============================================
echo ============================================
echo   Summary
echo ============================================
echo   Token:        !TOKEN!
echo   Server ID:    !SERVER!
if "!LOGO!"=="" (
    echo   Logo:         ^(none^)
) else (
    echo   Logo:         !LOGO!
)
echo   Target:       !OUTDIR!\PyCord.exe
echo ============================================
echo.
choice /C YN /M "Build EXE now"
if errorlevel 2 (
    echo Cancelled.
    pause
    exit /b 0
)
echo.

:: ============================================
:: 8. Clean up old build files
:: ============================================
echo Cleaning up old build files...
if exist "build" rmdir /S /Q "build" >nul 2>&1
if exist "dist"  rmdir /S /Q "dist"  >nul 2>&1
if exist "PyCord.spec" del /Q "PyCord.spec" >nul 2>&1
echo [OK] Cleaned up.
echo.

:: ============================================
:: 9. PyInstaller command  (NOCONSOLE!)
:: ============================================
echo Building EXE with PyInstaller...
echo.

set "PYI_CMD=pyinstaller --noconfirm --onefile --noconsole --name PyCord --add-data "Data.txt;.""

if not "!LOGO!"=="" (
    set "PYI_CMD=!PYI_CMD! --icon "!LOGO!""
)

set "PYI_CMD=!PYI_CMD! PyCord.py"

echo Command: !PYI_CMD!
echo.

%PYI_CMD%

if %errorlevel% neq 0 (
    echo.
    echo ERROR: PyInstaller failed!
    pause
    exit /b 1
)

echo.
echo [OK] Build complete.
echo.

:: ============================================
:: 10. Copy EXE directly to Desktop
:: ============================================
echo Copying EXE to Desktop...

if exist "!OUTDIR!\PyCord.exe" del /Q "!OUTDIR!\PyCord.exe" >nul 2>&1

copy /Y "dist\PyCord.exe" "!OUTDIR!\PyCord.exe" >nul

if not exist "!OUTDIR!\PyCord.exe" (
    echo ERROR: EXE could not be copied!
    pause
    exit /b 1
)

echo [OK] PyCord.exe is now on the Desktop.
echo.

:: ============================================
:: 11. Cleanup
:: ============================================
if exist "build" rmdir /S /Q "build" >nul 2>&1
if exist "dist"  rmdir /S /Q "dist"  >nul 2>&1
if exist "PyCord.spec" del /Q "PyCord.spec" >nul 2>&1

:: ============================================
:: Done
:: ============================================
echo ============================================
echo   DONE!
echo ============================================
echo   The EXE is located here:
echo   !OUTDIR!\PyCord.exe
echo ============================================
echo.
echo Press any key to close...
pause >nul
endlocal
exit /b 0