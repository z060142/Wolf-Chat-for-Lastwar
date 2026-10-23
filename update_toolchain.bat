@echo off
REM ============================================================
REM Wolf Chat - Toolchain security update
REM ============================================================
REM For the eMudhra / emSign CA incident (2026-10). This script:
REM   1. Updates every uv on PATH to the latest release
REM   2. Updates pip / certifi of the system Python interpreters
REM   3. Updates pip / certifi inside the project .venv
REM Minimum safe versions: uv 0.13.4, pip 26.2.2, certifi 2026.10.19
REM
REM Usage:
REM   update_toolchain.bat           check and update
REM   update_toolchain.bat --check   report only
REM Run as administrator if a Python is installed under Program Files.
REM ============================================================

setlocal
cd /d "%~dp0"

REM Pick an interpreter to run the updater (any Python 3.8+ works)
set "RUNNER="
if exist ".venv\Scripts\python.exe" (
    set "RUNNER=.venv\Scripts\python.exe"
    goto :run
)
where py >nul 2>&1
if not errorlevel 1 (
    set "RUNNER=py -3"
    goto :run
)
where python >nul 2>&1
if not errorlevel 1 (
    set "RUNNER=python"
    goto :run
)
echo ERROR: No Python interpreter found.
pause
exit /b 1

:run
echo Using: %RUNNER%
echo.
%RUNNER% scripts\update_toolchain.py %*
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
    echo Done. All checked tools are at or above the safe versions.
) else (
    echo Some items need attention - see the summary above.
)
pause
exit /b %RESULT%
