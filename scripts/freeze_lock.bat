@echo off
REM ============================================================
REM Wolf Chat - Regenerate requirements.lock.txt
REM ============================================================
REM Freezes the CURRENT .venv into requirements.lock.txt.
REM Only run this after the bot has been tested with this .venv.
REM start.bat then syncs every other installation to exactly this set.
REM ============================================================

setlocal
cd /d "%~dp0.."

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: .venv not found. Run start.bat first.
    pause
    exit /b 1
)

"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
    echo ERROR: .venv is not Python 3.12. The lock file must be generated on Python 3.12.
    pause
    exit /b 1
)

echo # Wolf Chat - locked dependency versions [Windows, CPython 3.12]> requirements.lock.tmp
echo # Generated from a verified working .venv with: scripts\freeze_lock.bat>> requirements.lock.tmp
echo # start.bat installs exactly this set with uv pip sync - extra packages are removed.>> requirements.lock.tmp
echo # Edit requirements.txt for top-level dependencies, then re-freeze after testing.>> requirements.lock.tmp
echo.>> requirements.lock.tmp
uv pip freeze --python "%VENV_PY%" >> requirements.lock.tmp
if errorlevel 1 (
    echo ERROR: uv pip freeze failed
    del requirements.lock.tmp
    pause
    exit /b 1
)

move /y requirements.lock.tmp requirements.lock.txt >nul
echo requirements.lock.txt updated.
echo Commit it together with your code changes.
pause
exit /b 0
