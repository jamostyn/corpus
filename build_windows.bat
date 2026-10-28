@echo off
REM ===========================================================================
REM  Corpus - Windows build script
REM
REM  PyInstaller cannot cross-compile: a Windows .exe has to be built ON
REM  Windows. This script is shipped inside Corpus-v<version>-windows-src.zip
REM  so you can produce the .exe yourself from the same source the macOS
REM  app was built from.
REM
REM  WHAT YOU NEED FIRST
REM    Python 3.11 or newer from python.org (NOT the Microsoft Store build -
REM    it sandboxes file access and Corpus writes to your chosen corpus
REM    folder). Tick "Add python.exe to PATH" in the installer.
REM
REM  HOW TO RUN
REM    Unzip anywhere, then double-click build_windows.bat.
REM    Takes a few minutes, mostly downloading dependencies.
REM
REM  WHAT YOU GET
REM    dist\Corpus\Corpus.exe  - plus an _internal folder it needs.
REM    Keep the whole dist\Corpus folder together; the .exe alone will
REM    not run. Make a shortcut to the .exe if you want it on the desktop.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ==========================================
echo   Building Corpus for Windows
echo ==========================================
echo.

REM ---- 1. Find Python ------------------------------------------------------
REM `py` is the launcher shipped with python.org installs; `python` is the
REM fallback for PATH-only setups. Checking both avoids the most common
REM "it says Python isn't installed but it is" support question.
set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if "!PYTHON!"=="" (
    where python >nul 2>&1 && set PYTHON=python
)
if "!PYTHON!"=="" (
    echo ERROR: Python was not found.
    echo.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation.
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

echo Using Python: !PYTHON!
!PYTHON! --version
echo.

REM ---- 2. Virtual environment ---------------------------------------------
REM Built in-place so repeat runs are fast and nothing touches the system
REM Python's site-packages.
if not exist ".venv" (
    echo Creating virtual environment...
    !PYTHON! -m venv .venv
    if errorlevel 1 (
        echo ERROR: could not create the virtual environment.
        pause
        exit /b 1
    )
)

set VENV_PY=.venv\Scripts\python.exe
if not exist "!VENV_PY!" (
    echo ERROR: virtual environment looks broken - !VENV_PY! is missing.
    echo Delete the .venv folder and run this script again.
    pause
    exit /b 1
)

REM ---- 3. Dependencies -----------------------------------------------------
echo.
echo Installing dependencies (this is the slow part)...
"!VENV_PY!" -m pip install --upgrade pip --quiet
"!VENV_PY!" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: installing runtime dependencies failed.
    echo Check your internet connection and try again.
    pause
    exit /b 1
)
"!VENV_PY!" -m pip install -r requirements-build.txt --quiet
if errorlevel 1 (
    echo ERROR: installing PyInstaller failed.
    pause
    exit /b 1
)

REM pywebview needs a .NET bridge for the Edge WebView2 backend on Windows.
REM It is not in requirements.txt because it is Windows-only and would
REM fail to install on macOS.
echo Installing the Windows WebView bridge...
"!VENV_PY!" -m pip install pythonnet --quiet
if errorlevel 1 (
    echo WARNING: pythonnet did not install.
    echo The build will continue, but Corpus may fail to open its window.
    echo.
)

REM ---- 4. Build ------------------------------------------------------------
echo.
echo Running PyInstaller...
"!VENV_PY!" -m PyInstaller pyinstaller_corpus.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo ERROR: the build failed. The PyInstaller output above says why.
    pause
    exit /b 1
)

if not exist "dist\Corpus\Corpus.exe" (
    echo.
    echo ERROR: PyInstaller finished but dist\Corpus\Corpus.exe is missing.
    pause
    exit /b 1
)

REM ---- 5. Done -------------------------------------------------------------
echo.
echo ==========================================
echo   Build complete
echo ==========================================
echo.
echo   dist\Corpus\Corpus.exe
echo.
echo Keep the whole dist\Corpus folder together - the .exe needs the
echo _internal folder beside it. Right-click the .exe and "Send to =^>
echo Desktop (create shortcut)" if you want it handy.
echo.
echo First launch will ask where to keep your papers. Pick any folder.
echo.
echo NOTE: Windows SmartScreen may warn that the app is unrecognised,
echo because this build is not code-signed. Click "More info" then
echo "Run anyway".
echo.
pause
