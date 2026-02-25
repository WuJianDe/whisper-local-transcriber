@echo off
chcp 65001 >nul
echo ======================================
echo   Whisper Transcription - Install
echo ======================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Python found.
echo.
echo [*] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Upgrading pip...
python -m pip install --upgrade pip -q

echo [*] Installing openai-whisper and flask...
echo     (This may take a few minutes on first run)
pip install openai-whisper flask

if errorlevel 1 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo.
echo ======================================
echo   Installation complete!
echo   Run start.bat to launch the app.
echo ======================================
pause
