@echo off
REM ============================================================
REM Wolf Chat - Main Launcher Script
REM ============================================================
REM This script:
REM 1. Checks for administrator privileges (optional)
REM 2. Sets up UV environment if needed
REM 3. Launches Setup.py
REM ============================================================

setlocal enabledelayedexpansion

REM Store the current directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================================
echo Wolf Chat - Launcher
echo ============================================================
echo.

REM Check if running with administrator privileges
call scripts\check_admin.bat
if errorlevel 1 (
    echo WARNING: Not running as administrator
    echo Requesting administrator privileges and restarting...
    echo.
    cscript //NoLogo scripts\request_admin.vbs "%~f0"
    exit
) else (
    echo Running with administrator privileges
    echo.
)

REM Check if .venv exists
if not exist ".venv\" (
    echo Virtual environment not found at '.venv\'
    echo.
    echo Running UV environment setup...
    echo.
    call scripts\setup_uv_env.bat

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to set up environment
        echo.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment found at '.venv\'

    REM Check if requirements have changed
    if exist ".venv\.requirements_hash" (
        REM Calculate current requirements hash
        for /f %%i in ('certutil -hashfile requirements.txt SHA256 ^| find /v "hash"') do set "CURRENT_HASH=%%i"
        set /p OLD_HASH=<.venv\.requirements_hash

        if not "!CURRENT_HASH!"=="!OLD_HASH!" (
            echo.
            echo WARNING: requirements.txt has changed since last setup
            set /p UPDATE="Do you want to update dependencies? (y/n): "
            if /i "!UPDATE!"=="y" (
                echo Updating dependencies with UV...
                call .venv\Scripts\activate.bat
                uv pip install -r requirements.txt

                if errorlevel 1 (
                    echo.
                    echo ERROR: Failed to update dependencies
                    echo.
                    pause
                    exit /b 1
                )

                REM Update hash
                echo !CURRENT_HASH!>.venv\.requirements_hash
            )
        )
    ) else (
        REM First time - create hash
        for /f %%i in ('certutil -hashfile requirements.txt SHA256 ^| find /v "hash"') do set "CURRENT_HASH=%%i"
        echo !CURRENT_HASH!>.venv\.requirements_hash
    )
    echo.
)

REM Install Chroma MCP if needed (first-time setup)
echo Checking Chroma MCP installation...

REM Check if chroma-mcp is installed in the virtual environment
.venv\Scripts\python.exe -c "import chroma_mcp" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ============================================================
    echo Chroma MCP not installed - Installing latest version
    echo ============================================================
    echo.

    REM Define download URL and temporary folder
    set "DOWNLOAD_URL=https://github.com/chroma-core/chroma-mcp/releases/download/v0.2.6/chroma_mcp-0.2.6-py3-none-any.whl"
    set "TEMP_FOLDER=temp_chroma_install"
    set "WHL_FILE=chroma_mcp-0.2.6-py3-none-any.whl"

    echo [1/4] Creating temporary download folder...
    if exist "!TEMP_FOLDER!\" (
        rmdir /s /q "!TEMP_FOLDER!"
    )
    mkdir "!TEMP_FOLDER!"
    if errorlevel 1 (
        echo ERROR: Failed to create temporary folder
        pause
        exit /b 1
    )
    echo.

    echo [2/4] Downloading Chroma MCP v0.2.6...
    echo This may take a moment depending on your internet connection...
    echo.
    powershell -Command "& {$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!TEMP_FOLDER!\!WHL_FILE!'}"

    if errorlevel 1 (
        echo ERROR: Failed to download package
        rmdir /s /q "!TEMP_FOLDER!"
        pause
        exit /b 1
    )

    if not exist "!TEMP_FOLDER!\!WHL_FILE!" (
        echo ERROR: Downloaded file not found
        rmdir /s /q "!TEMP_FOLDER!"
        pause
        exit /b 1
    )
    echo Download completed successfully
    echo.

    echo [3/4] Installing Chroma MCP with UV...
    echo.
    uv pip install "!TEMP_FOLDER!\!WHL_FILE!"

    if errorlevel 1 (
        echo ERROR: Failed to install Chroma MCP
        rmdir /s /q "!TEMP_FOLDER!"
        pause
        exit /b 1
    )
    echo.

    echo [4/4] Cleaning up temporary files...
    rmdir /s /q "!TEMP_FOLDER!"
    echo.

    echo ============================================================
    echo Chroma MCP v0.2.6 installed successfully!
    echo ============================================================
    echo.
) else (
    echo Chroma MCP already installed
    echo.
)

REM Check if Setup.py exists
if not exist "Setup.py" (
    echo.
    echo ERROR: Setup.py not found in current directory
    echo Please ensure you're running this script from the Wolf Chat directory
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo Starting Wolf Chat Setup...
echo ============================================================
echo.

REM Run Setup.py using virtual environment Python
.venv\Scripts\python.exe Setup.py

if errorlevel 1 (
    echo.
    echo ERROR: Setup.py exited with error
    echo.
    pause
    exit /b 1
)

REM Keep window open if run directly (not from another script)
echo.
echo ============================================================
echo Setup completed
echo ============================================================
pause
