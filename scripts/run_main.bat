@echo off
REM ============================================================
REM Wolf Chat - Run Main Application
REM ============================================================
REM This script activates the UV environment and runs main.py
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - Main Application Launcher
echo ============================================================
echo.

REM Check if .venv exists
if not exist ".venv\" (
    echo ERROR: Virtual environment not found at '.venv\'
    echo Please run start.bat first to set up the environment
    echo.
    pause
    exit /b 1
)

REM Check if main.py exists
if not exist "main.py" (
    echo ERROR: main.py not found in current directory
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    echo.
    pause
    exit /b 1
)

echo Starting Wolf Chat...
echo.
echo ============================================================
echo.

REM Run main.py
python main.py

if errorlevel 1 (
    echo.
    echo ERROR: main.py exited with error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Application closed
echo ============================================================
pause
