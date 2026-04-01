@echo off
REM ============================================================
REM Wolf Chat - System Prompt Tester Launcher
REM ============================================================
REM This script activates the UV environment and launches
REM the system prompt tester for testing prompt configurations
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - System Prompt Tester
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

REM Check if system_prompt_tester.py exists
if not exist "system_prompt_tester.py" (
    echo ERROR: system_prompt_tester.py not found
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

echo Starting System Prompt Tester...
echo.
echo ============================================================
echo.
echo This tool allows you to test and preview system prompts
echo You can test different MCP server combinations and scenarios
echo.
echo ============================================================
echo.

REM Run system_prompt_tester.py
python system_prompt_tester.py

if errorlevel 1 (
    echo.
    echo ERROR: System Prompt Tester exited with error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo System Prompt Tester closed
echo ============================================================
pause
