@echo off
setlocal EnableDelayedExpansion
title Python Setup - Installation

:: ============================================
:: Restart as administrator if needed
:: ============================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator rights are required...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo   Python + Module Installer
echo ============================================
echo.

:: ============================================
:: 1. Check / install Python
:: ============================================
echo [1/4] Checking if Python is installed...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo    Python is already installed:
    python --version
    goto :python_ok
)

echo    Python not found. Installing Python 3.12...
echo.

set "PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
set "PY_INSTALLER=%TEMP%\python_installer.exe"

echo    Downloading Python...
powershell -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'"
if not exist "%PY_INSTALLER%" (
    echo    ERROR: Download failed!
    pause
    exit /b 1
)

echo    Installing Python (this may take a few minutes)...
"%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1

set "PATH=%PATH%;C:\Program Files\Python312;C:\Program Files\Python312\Scripts"

timeout /t 5 /nobreak >nul

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    ERROR: Python could not be installed!
    pause
    exit /b 1
)
echo    Python installed successfully.

:python_ok
echo.

:: ============================================
:: 2. Update pip
:: ============================================
echo [2/4] Updating pip...
python -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo    WARNING: pip update failed.
)
echo.

:: ============================================
:: 3. Install all modules
:: ============================================
echo [3/4] Installing required modules...
echo.

set "MODULES=discord.py aiohttp psutil pyinstaller auto-py-to-exe"

for %%M in (%MODULES%) do (
    echo    Installing %%M ...
    python -m pip install --upgrade %%M
    if !errorlevel! neq 0 (
        echo    WARNING: %%M could not be installed.
    )
)

echo.
echo    Note: Standard libraries (uuid, socket, re,
echo    platform, getpass, datetime, os, subprocess,
echo    asyncio, urllib, concurrent.futures, threading,
echo    shutil, zipfile, io, sys, ctypes, tempfile,
echo    winreg, time) are already included with Python.
echo.

:: ============================================
:: 4. Verification
:: ============================================
echo [4/4] Verifying installation...
echo.

python -c "import discord; print('  [OK] discord', discord.__version__)"
python -c "import aiohttp; print('  [OK] aiohttp', aiohttp.__version__)"
python -c "import psutil; print('  [OK] psutil', psutil.__version__)"
python -c "import PyInstaller; print('  [OK] PyInstaller', PyInstaller.__version__)"

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.

:: ============================================
:: Start builder.cmd
:: ============================================
set "BUILDER=%~dp0builder.cmd"

if exist "%BUILDER%" (
    echo Starting builder.cmd ...
    echo.
    timeout /t 2 /nobreak >nul
    call "%BUILDER%"
) else (
    echo ERROR: builder.cmd was not found!
    echo Expected at: %BUILDER%
    echo.
    echo Please make sure builder.cmd is in the same
    echo folder as this install.bat.
    echo.
    pause
)

endlocal