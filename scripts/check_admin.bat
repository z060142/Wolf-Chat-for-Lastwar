@echo off
REM ============================================================
REM Check Administrator Privileges
REM ============================================================
REM This script checks if running with administrator privileges
REM Returns errorlevel 0 if admin, 1 if not
REM ============================================================

net session >nul 2>&1
if %errorlevel% == 0 (
    REM Running as administrator
    exit /b 0
) else (
    REM Not running as administrator
    exit /b 1
)
