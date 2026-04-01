@echo off
REM ============================================================
REM Wolf Chat - Chroma MCP Installation Script
REM ============================================================
REM This script:
REM 1. Creates a temporary download folder
REM 2. Downloads chroma_mcp-0.2.6-py3-none-any.whl
REM 3. Installs the package using UV
REM 4. Cleans up temporary files
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory and navigate to project root
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%.."

echo.
echo ============================================================
echo Chroma MCP Installation
echo ============================================================
echo.

REM Define download URL and temporary folder
set "DOWNLOAD_URL=https://github.com/chroma-core/chroma-mcp/releases/download/v0.2.6/chroma_mcp-0.2.6-py3-none-any.whl"
set "TEMP_FOLDER=temp_chroma_install"
set "WHL_FILE=chroma_mcp-0.2.6-py3-none-any.whl"

REM Check if UV is installed
echo [1/5] Checking UV installation...
where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: UV is not installed
    echo Please run scripts\setup_uv_env.bat first to install UV
    echo.
    pause
    exit /b 1
)
echo UV found:
uv --version
echo.

REM Check if virtual environment exists
if not exist ".venv\" (
    echo.
    echo ERROR: Virtual environment not found at '.venv\'
    echo Please run scripts\setup_uv_env.bat first to create the environment
    echo.
    pause
    exit /b 1
)
echo [2/5] Virtual environment found at '.venv\'
echo.

REM Create temporary folder
echo [3/5] Creating temporary download folder...
if exist "%TEMP_FOLDER%\" (
    echo Cleaning existing temporary folder...
    rmdir /s /q "%TEMP_FOLDER%"
)
mkdir "%TEMP_FOLDER%"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to create temporary folder
    echo.
    pause
    exit /b 1
)
echo Temporary folder created: %TEMP_FOLDER%
echo.

REM Download the .whl file
echo [4/5] Downloading Chroma MCP package...
echo URL: %DOWNLOAD_URL%
echo.
echo This may take a moment depending on your internet connection...
echo.

REM Use PowerShell to download the file with progress
powershell -Command "& {$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%TEMP_FOLDER%\%WHL_FILE%'}"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to download the package
    echo Please check your internet connection and try again
    echo.
    rmdir /s /q "%TEMP_FOLDER%"
    pause
    exit /b 1
)

if not exist "%TEMP_FOLDER%\%WHL_FILE%" (
    echo.
    echo ERROR: Downloaded file not found
    echo.
    rmdir /s /q "%TEMP_FOLDER%"
    pause
    exit /b 1
)

echo Download completed successfully
echo File location: %TEMP_FOLDER%\%WHL_FILE%
echo.

REM Install the package using UV
echo [5/5] Installing Chroma MCP package with UV...
echo.

uv pip install "%TEMP_FOLDER%\%WHL_FILE%"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Chroma MCP
    echo The downloaded file is preserved in %TEMP_FOLDER% for manual inspection
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Installation completed successfully!
echo ============================================================
echo.
echo Chroma MCP v0.2.6 has been installed to your virtual environment
echo.

REM Clean up temporary folder
echo Cleaning up temporary files...
rmdir /s /q "%TEMP_FOLDER%"
echo Temporary files removed
echo.

REM Verify installation
echo Verifying installation...
uv pip list | findstr /C:"chroma-mcp" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo Package verification successful:
    uv pip list | findstr /C:"chroma"
    echo.
) else (
    echo.
    echo WARNING: Package installed but not found in package list
    echo This may be normal - please verify manually if needed
    echo.
)

echo ============================================================
echo.
echo To use Chroma MCP, configure it in your MCP servers setup
echo See config.py for MCP server configuration examples
echo.
echo ============================================================
pause
exit /b 0
