@echo off
REM ============================================================
REM Wolf Chat - LLM Debug Script Launcher
REM ============================================================
REM This script activates the UV environment and launches
REM the LLM debug script for testing prompts and tool calls
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%\.."

echo.
echo ============================================================
echo Wolf Chat - LLM Debug Script
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

REM Check if llm_debug_script.py exists
if not exist "test\llm_debug_script.py" (
    echo ERROR: llm_debug_script.py not found at 'test\llm_debug_script.py'
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

echo Starting LLM Debug Script...
echo.
echo ============================================================
echo.
echo This tool allows you to test LLM interactions without UI
echo You can test prompts, tool calls, and MCP server responses
echo.
echo ============================================================
echo.

REM Run llm_debug_script.py
python test\llm_debug_script.py

if errorlevel 1 (
    echo.
    echo ERROR: LLM Debug Script exited with error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo LLM Debug Script closed
echo ============================================================
pause
