@echo off
REM ============================================================
REM Wolf Chat - UV Environment Setup Script (Windows)
REM ============================================================
REM This script installs UV and sets up the Python environment
REM using UV package manager for faster dependency installation
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo Wolf Chat - UV Environment Setup
echo ============================================================
echo.

REM Check if UV is already installed
where uv >nul 2>&1
if errorlevel 1 (
    echo [1/5] UV not found. Installing UV...
    echo.
    echo Downloading and installing UV package manager...
    echo This may take a moment...
    echo.

    REM Install UV using PowerShell
    powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install UV
        echo Please install UV manually from: https://github.com/astral-sh/uv
        echo.
        pause
        exit /b 1
    )

    REM Refresh environment variables
    echo.
    echo Refreshing environment variables...
    call :RefreshPath

    REM Check again after installation
    where uv >nul 2>&1
    if errorlevel 1 (
        echo.
        echo WARNING: UV installed but not found in PATH
        echo You may need to restart your terminal or add UV to PATH manually
        echo Default location: %USERPROFILE%\.cargo\bin
        echo.
        pause
        exit /b 1
    )

    echo UV installed successfully!
    echo.
) else (
    echo [1/5] UV is already installed
    uv --version
    echo.
)

REM Python 3.12 is required: requirements.lock.txt is resolved and verified on CPython 3.12
echo [2/5] Detecting Python 3.12...
echo.

set "PYTHON_VERSION=3.12"
uv python find 3.12 >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 not found. Installing Python 3.12 via UV...
    echo.
    uv python install 3.12
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install Python via UV
        echo Please install Python 3.12 manually from https://www.python.org/
        echo.
        pause
        exit /b 1
    )
    echo Python 3.12 installed successfully
) else (
    echo Found Python 3.12
)

echo.
echo Selected Python version: !PYTHON_VERSION!
echo.

REM Check if .venv already exists
if exist ".venv\" (
    echo.
    echo WARNING: Virtual environment already exists at '.venv\'
    set /p OVERWRITE="Do you want to recreate it? (y/n): "
    if /i not "!OVERWRITE!"=="y" (
        echo.
        echo Setup cancelled. Using existing virtual environment.
        echo start.bat will sync packages with requirements.lock.txt.
        echo.
        pause
        exit /b 0
    )
    echo.
    echo [3/5] Removing existing virtual environment...
    rmdir /s /q .venv
)

echo.
echo [3/5] Creating virtual environment with UV (Python !PYTHON_VERSION!)...
uv venv --python !PYTHON_VERSION!

if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment
    echo.
    pause
    exit /b 1
)

echo Virtual environment created successfully at '.venv\'
echo.

echo [4/5] Installing dependencies from requirements.lock.txt...
echo This may take several minutes depending on your internet connection...
echo UV will cache packages for faster future installations
echo.

REM Install exactly the locked (verified) package set
uv pip sync --python .venv\Scripts\python.exe requirements.lock.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies from requirements.lock.txt
    echo Please check the requirements.lock.txt file and your internet connection
    echo.
    pause
    exit /b 1
)

REM [Chroma deprecated] sentence-transformers embedding model is no longer needed
REM echo.
REM echo ============================================================
REM echo Downloading embedding model...
REM echo ============================================================
REM echo.
REM echo This will download the sentence-transformers model for multilingual embeddings...
REM echo Model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2
REM echo.
REM call .venv\Scripts\activate.bat
REM python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2'); print('Model downloaded successfully!')"
REM if errorlevel 1 (
REM     echo.
REM     echo WARNING: Failed to download embedding model
REM     echo You may need to download it manually later
REM     echo.
REM ) else (
REM     echo.
REM     echo Embedding model downloaded successfully!
REM     echo.
REM )
echo.
echo [5/5] Setup Complete!
echo ============================================================
echo.
echo Virtual environment has been created with UV and all dependencies installed.
echo.
echo UV Benefits:
echo   - 10-100x faster than pip
echo   - Automatic dependency resolution
echo   - Built-in caching for offline usage
echo.
echo To activate the environment manually:
echo   - Windows: .venv\Scripts\activate.bat
echo   - To deactivate: deactivate
echo.
echo To add new packages:
echo   - uv pip install package-name
echo   - Add it to requirements.txt, test, then run scripts\freeze_lock.bat
echo.
echo ============================================================

exit /b 0

:RefreshPath
REM Refresh PATH from registry without restarting
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "UserPath=%%b"
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SystemPath=%%b"
set "PATH=%UserPath%;%SystemPath%;%USERPROFILE%\.cargo\bin"
exit /b 0
