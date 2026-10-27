@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================================
echo   Whisper Local Transcriber - Smart Launcher
echo ====================================================
echo.

if not exist "venv\Scripts\python.exe" goto :INSTALL

venv\Scripts\python.exe -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [!] Detected broken venv, removing old venv...
    rmdir /s /q venv
    goto :INSTALL
)

venv\Scripts\python.exe -c "import faster_whisper, opencc, flask" >nul 2>&1
if errorlevel 1 goto :INSTALL

echo [OK] Environment ready. Starting server...
goto :RUN

:INSTALL
echo [*] Setting up Python environment and packages...
set "SYS_PY="

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "SYS_PY=%%D\python.exe"
)
if defined SYS_PY goto :FOUND_PY

for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" set "SYS_PY=%%D\python.exe"
)
if defined SYS_PY goto :FOUND_PY

python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY=python"
    goto :FOUND_PY
)

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "SYS_PY=py -3"
    goto :FOUND_PY
)

echo [!] Python 3.10+ not found on this PC.
where winget >nul 2>&1
if errorlevel 1 goto :NO_PYTHON

echo [*] Downloading and installing Python 3.12 via winget...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "SYS_PY=%%D\python.exe"
)
if defined SYS_PY goto :FOUND_PY

:NO_PYTHON
echo.
echo [ERROR] Python 3.10+ is not installed!
echo Please download and install Python 3.12 from:
echo https://www.python.org/downloads/
echo (Remember to check "Add python.exe to PATH" during installation)
echo.
pause
exit /b 1

:FOUND_PY
echo [OK] Using Python: %SYS_PY%

if exist "venv\Scripts\python.exe" goto :INSTALL_DEPS
echo [*] Creating virtual environment (venv)...
"%SYS_PY%" -m venv venv
if errorlevel 1 (
    %SYS_PY% -m venv venv
)
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Failed to create virtual environment (venv).
    pause
    exit /b 1
)

:INSTALL_DEPS
echo [*] Installing required packages (faster-whisper, opencc, flask)...
echo     (First-time installation takes 1-3 minutes, please wait...)
venv\Scripts\python.exe -m pip install --upgrade pip -q
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Please check your internet connection.
    pause
    exit /b 1
)
echo [OK] Installation complete!

:RUN
echo.
echo [*] Launching Whisper server...
venv\Scripts\python.exe app.py
echo.
pause
