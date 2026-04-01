@echo off
REM ============================================================
REM Wolf Chat - LLM Debug Script with Memory System
REM ============================================================
REM Usage:
REM   debug_memory.bat           - use real memory (wolf-memory/memories/)
REM   debug_memory.bat --test    - use isolated test memory (wolf-memory/memories_test/)
REM ============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check venv
if not exist ".venv\" (
    echo ERROR: Virtual environment not found. Please run start.bat first.
    pause
    exit /b 1
)

REM Parse --test flag
set "TEST_FLAG="
if "%~1"=="--test" set "TEST_FLAG=--test-memory"

REM Install wolf-memory dependencies if needed
echo Checking wolf-memory dependencies...
.venv\Scripts\python.exe -c "import frontmatter" >nul 2>&1
if errorlevel 1 (
    echo Installing wolf-memory dependencies...
    .venv\Scripts\python.exe -m pip install -r wolf-memory\requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install wolf-memory dependencies
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
if defined TEST_FLAG (
    echo LLM Debug - TEST MEMORY MODE
    echo Memory directory: wolf-memory\memories_test\
) else (
    echo LLM Debug - REAL MEMORY MODE
    echo Memory directory: wolf-memory\memories\
)
echo ============================================================
echo.

.venv\Scripts\python.exe test\llm_debug_script.py %TEST_FLAG%

echo.
pause
