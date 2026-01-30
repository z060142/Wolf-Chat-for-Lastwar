@echo off
REM ============================================================
REM Activate UV Virtual Environment
REM ============================================================
REM This script activates the UV-created virtual environment
REM and opens a command prompt with the environment active
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - Activate UV Environment
echo ============================================================
echo.

REM Check if .venv exists
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at '.venv\'
    echo Please run start.bat first to set up the environment
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ============================================================
echo Virtual environment activated!
echo ============================================================
echo.
echo You are now in the Wolf Chat UV environment.
echo.
echo Available commands:
echo   python Setup.py           - Run setup configuration
echo   python main.py            - Run main application
echo   uv pip install package    - Install new package
echo   uv pip list               - List installed packages
echo   deactivate                - Exit virtual environment
echo.
echo Type 'deactivate' when you want to exit the environment
echo.
echo ============================================================
echo.

cmd /k
