@echo off
setlocal enabledelayedexpansion

REM === Find Python ===
set "PYTHON="

REM Try common conda paths
for %%p in (
    "C:\ProgramData\Anaconda3\envs\email_audit\python.exe"
    "C:\Anaconda3\envs\email_audit\python.exe"
    "C:\Miniconda3\envs\email_audit\python.exe"
    "%USERPROFILE%\anaconda3\envs\email_audit\python.exe"
    "%USERPROFILE%\miniconda3\envs\email_audit\python.exe"
) do (
    if exist %%p set "PYTHON=%%~p"
)

REM If conda env not found, try system python with pyinstaller
if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where python') do (
            set "PYTHON=%%i"
            goto :found_python
        )
    )
)

if not defined PYTHON (
    echo [ERROR] Python not found. Please install Python or Anaconda.
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

:found_python
echo Using: %PYTHON%

REM === Install deps if needed ===
"%PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    "%PYTHON%" -m pip install -r requirements.txt pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

REM === Build ===
echo Building...
cd /d "%~dp0"
"%PYTHON%" -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done! Output: dist\EmailAudit.exe
echo ============================================
echo.
pause
