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

REM ============================================================
REM Python environment
REM   - .venv must be CPython 3.12 (requirements.lock.txt is resolved for 3.12)
REM   - Packages are synced to requirements.lock.txt with 'uv pip sync':
REM     missing packages are installed, wrong versions are replaced and
REM     packages not in the lock file (e.g. old chroma / torch) are removed.
REM   - Sync runs automatically when the lock file changed or a core import fails.
REM ============================================================
set "LOCK_FILE=requirements.lock.txt"
set "VENV_PY=.venv\Scripts\python.exe"
set "CORE_IMPORTS=import mcp, anthropic, openai, cv2, numpy, PIL, pyautogui, imagehash, scipy, pyperclip, keyboard, win32gui"

REM Create .venv if it does not exist
if not exist "%VENV_PY%" (
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
)

REM Check Python version of .venv
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: .venv is not Python 3.12. The locked dependencies require Python 3.12.
    set /p REBUILD="Rebuild .venv with Python 3.12 now? (y/n): "
    if /i "!REBUILD!"=="y" (
        echo Removing old virtual environment...
        rmdir /s /q .venv
        call scripts\setup_uv_env.bat
        if errorlevel 1 (
            echo.
            echo ERROR: Failed to rebuild environment
            echo.
            pause
            exit /b 1
        )
    ) else (
        echo Continuing with the existing .venv - dependency sync may fail.
    )
)

if not exist "%LOCK_FILE%" (
    echo.
    echo ERROR: %LOCK_FILE% not found
    echo.
    pause
    exit /b 1
)

REM Decide whether a dependency sync is needed
for /f %%i in ('certutil -hashfile %LOCK_FILE% SHA256 ^| find /v "hash"') do set "CURRENT_HASH=%%i"
set "OLD_HASH="
if exist ".venv\.requirements_hash" set /p OLD_HASH=<.venv\.requirements_hash
set "NEED_SYNC=0"
if not "!CURRENT_HASH!"=="!OLD_HASH!" (
    echo Dependency lock file changed since last sync.
    set "NEED_SYNC=1"
)
"%VENV_PY%" -c "%CORE_IMPORTS%" >nul 2>&1
if errorlevel 1 (
    echo Some core packages are missing or broken.
    set "NEED_SYNC=1"
)

if "!NEED_SYNC!"=="1" (
    echo.
    echo ============================================================
    echo Syncing dependencies with %LOCK_FILE%
    echo ============================================================
    echo Make sure the bot is NOT running, otherwise files may be locked.
    echo.
    uv pip sync --python "%VENV_PY%" "%LOCK_FILE%"
    if errorlevel 1 (
        echo.
        echo ERROR: Dependency sync failed.
        echo Close any running bot / Setup.py window and run start.bat again.
        echo If it keeps failing, delete the .venv folder and run start.bat to rebuild it.
        echo.
        pause
        exit /b 1
    )
    "%VENV_PY%" -c "%CORE_IMPORTS%"
    if errorlevel 1 (
        echo.
        echo ERROR: Core packages still fail to import after sync.
        echo Delete the .venv folder and run start.bat to rebuild it.
        echo.
        pause
        exit /b 1
    )
    echo !CURRENT_HASH!>.venv\.requirements_hash
    echo Dependencies are up to date.
) else (
    echo Dependencies are up to date.
)
echo.

REM [Chroma deprecated] Chroma MCP is no longer installed (it pins mcp==1.6.0 and breaks the main app).
REM The original install block is kept below as comments.
REM REM Install Chroma MCP if needed (first-time setup)
REM echo Checking Chroma MCP installation...
REM
REM REM Check if chroma-mcp is installed in the virtual environment
REM .venv\Scripts\python.exe -c "import chroma_mcp" >nul 2>&1
REM if errorlevel 1 (
REM     echo.
REM     echo ============================================================
REM     echo Chroma MCP not installed - Installing latest version
REM     echo ============================================================
REM     echo.
REM
REM     REM Define download URL and temporary folder
REM     set "DOWNLOAD_URL=https://github.com/chroma-core/chroma-mcp/releases/download/v0.2.6/chroma_mcp-0.2.6-py3-none-any.whl"
REM     set "TEMP_FOLDER=temp_chroma_install"
REM     set "WHL_FILE=chroma_mcp-0.2.6-py3-none-any.whl"
REM
REM     echo [1/4] Creating temporary download folder...
REM     if exist "!TEMP_FOLDER!\" (
REM         rmdir /s /q "!TEMP_FOLDER!"
REM     )
REM     mkdir "!TEMP_FOLDER!"
REM     if errorlevel 1 (
REM         echo ERROR: Failed to create temporary folder
REM         pause
REM         exit /b 1
REM     )
REM     echo.
REM
REM     echo [2/4] Downloading Chroma MCP v0.2.6...
REM     echo This may take a moment depending on your internet connection...
REM     echo.
REM     powershell -Command "& {$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!TEMP_FOLDER!\!WHL_FILE!'}"
REM
REM     if errorlevel 1 (
REM         echo ERROR: Failed to download package
REM         rmdir /s /q "!TEMP_FOLDER!"
REM         pause
REM         exit /b 1
REM     )
REM
REM     if not exist "!TEMP_FOLDER!\!WHL_FILE!" (
REM         echo ERROR: Downloaded file not found
REM         rmdir /s /q "!TEMP_FOLDER!"
REM         pause
REM         exit /b 1
REM     )
REM     echo Download completed successfully
REM     echo.
REM
REM     echo [3/4] Installing Chroma MCP with UV...
REM     echo.
REM     uv pip install "!TEMP_FOLDER!\!WHL_FILE!"
REM
REM     if errorlevel 1 (
REM         echo ERROR: Failed to install Chroma MCP
REM         rmdir /s /q "!TEMP_FOLDER!"
REM         pause
REM         exit /b 1
REM     )
REM     echo.
REM
REM     echo [4/4] Cleaning up temporary files...
REM     rmdir /s /q "!TEMP_FOLDER!"
REM     echo.
REM
REM     echo ============================================================
REM     echo Chroma MCP v0.2.6 installed successfully!
REM     echo ============================================================
REM     echo.
REM ) else (
REM     echo Chroma MCP already installed
REM     echo.
REM )

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
