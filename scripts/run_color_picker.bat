@echo off
REM ============================================================
REM Wolf Chat - Color Picker Tool Launcher
REM ============================================================
REM This script activates the UV environment and launches
REM the color picker tool for UI template matching configuration
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - Color Picker Tool
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

REM Check if color_picker.py exists
if not exist "tools\color_picker.py" (
    echo ERROR: color_picker.py not found at 'tools\color_picker.py'
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

echo Starting Color Picker Tool...
echo.
echo ============================================================
echo.
echo Instructions:
echo 1. The tool will capture the game area screenshot
echo 2. Click on chat bubble areas to sample colors
echo 3. Press 'q' to quit and save the color configuration
echo.
echo ============================================================
echo.

REM Run color_picker.py
python tools\color_picker.py

if errorlevel 1 (
    echo.
    echo ERROR: Color Picker exited with error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Color Picker closed
echo ============================================================
pause
