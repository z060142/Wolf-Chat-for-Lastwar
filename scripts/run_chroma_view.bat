@echo off
REM ============================================================
REM Wolf Chat - ChromaDB Viewer Launcher
REM ============================================================
REM This script activates the UV environment and launches
REM the ChromaDB viewer tool for inspecting memory data
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - ChromaDB Viewer
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

REM Check if chroma_view.py exists
if not exist "tools\chroma_view.py" (
    echo ERROR: chroma_view.py not found at 'tools\chroma_view.py'
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

echo Starting ChromaDB Viewer...
echo.
echo ============================================================
echo.

REM Run chroma_view.py
python tools\chroma_view.py

if errorlevel 1 (
    echo.
    echo ERROR: ChromaDB Viewer exited with error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo ChromaDB Viewer closed
echo ============================================================
pause
