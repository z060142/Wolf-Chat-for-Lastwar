@echo off
REM ============================================================
REM Wolf Chat - Virtual Environment Setup Script (Windows)
REM ============================================================
REM This script creates a Python virtual environment and installs
REM all required dependencies from requirements.txt
REM ============================================================

echo.
echo ============================================================
echo Wolf Chat - Virtual Environment Setup
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Python version...
python --version

REM Check if venv already exists
if exist "venv\" (
    echo.
    echo WARNING: Virtual environment already exists at 'venv\'
    set /p OVERWRITE="Do you want to recreate it? (y/n): "
    if /i not "%OVERWRITE%"=="y" (
        echo.
        echo Setup cancelled. Using existing virtual environment.
        echo To install/update packages, run: venv\Scripts\activate.bat
        echo Then run: pip install -r requirements.txt
        echo.
        pause
        exit /b 0
    )
    echo.
    echo [2/4] Removing existing virtual environment...
    rmdir /s /q venv
)

echo.
echo [2/4] Creating virtual environment...
python -m venv venv

if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment
    echo Please ensure you have python3-venv installed
    echo.
    pause
    exit /b 1
)

echo [2/4] Virtual environment created successfully at 'venv\'

echo.
echo [3/4] Activating virtual environment...
call venv\Scripts\activate.bat

if errorlevel 1 (
    echo.
    echo ERROR: Failed to activate virtual environment
    echo.
    pause
    exit /b 1
)

echo [3/4] Virtual environment activated

echo.
echo [4/4] Installing dependencies from requirements.txt...
echo This may take several minutes depending on your internet connection...
echo.

REM Upgrade pip first
python -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo WARNING: Failed to upgrade pip, continuing with current version...
)

REM Install requirements
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies from requirements.txt
    echo Please check the requirements.txt file and your internet connection
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Creating launcher scripts...
echo ============================================================
echo.

REM Create run_setup.bat
echo Creating run_setup.bat...
(
echo @echo off
echo REM Launch Setup.py in Virtual Environment
echo.
echo if not exist "venv\Scripts\activate.bat" ^(
echo     echo ERROR: Virtual environment not found
echo     pause
echo     exit /b 1
echo ^)
echo.
echo if not exist "Setup.py" ^(
echo     echo ERROR: Setup.py not found
echo     pause
echo     exit /b 1
echo ^)
echo.
echo call venv\Scripts\activate.bat
echo python Setup.py
echo pause
) > run_setup.bat

REM Create activate_venv.bat
echo Creating activate_venv.bat...
(
echo @echo off
echo REM Activate Virtual Environment
echo.
echo if not exist "venv\Scripts\activate.bat" ^(
echo     echo ERROR: Virtual environment not found
echo     pause
echo     exit /b 1
echo ^)
echo.
echo call venv\Scripts\activate.bat
echo echo Virtual environment activated!
echo echo Type 'deactivate' to exit the environment
echo cmd /k
) > activate_venv.bat

echo.
echo ============================================================
echo Setup Complete!
echo ============================================================
echo.
echo Virtual environment has been created and all dependencies installed.
echo.
echo Launcher scripts created:
echo   - run_setup.bat      : Launch Setup.py in venv
echo   - activate_venv.bat  : Activate venv environment only
echo.
echo To use the virtual environment:
echo   - Run 'activate_venv.bat' to activate the environment
echo   - Run 'run_setup.bat' to launch Setup.py
echo   - Or manually: venv\Scripts\activate.bat
echo.
echo To deactivate the environment, simply type: deactivate
echo.
echo ============================================================
pause
