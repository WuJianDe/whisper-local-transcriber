@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================================
echo   Whisper 本地語音轉逐字稿系統 - 智慧啟動器
echo ====================================================

set "NEED_INSTALL=0"

:: 1. 檢查虛擬環境中的 Python 是否存在且可用
if not exist "venv\Scripts\python.exe" (
    set "NEED_INSTALL=1"
) else (
    venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [!] 偵測到舊的虛擬環境已失效，準備重新建立...
        rmdir /s /q venv
        set "NEED_INSTALL=1"
    )
)

:: 2. 若虛擬環境存在，檢查核心套件 (faster_whisper, opencc, flask) 是否已安裝
if "%NEED_INSTALL%"=="0" (
    venv\Scripts\python.exe -c "import faster_whisper, opencc, flask" >nul 2>&1
    if errorlevel 1 (
        set "NEED_INSTALL=1"
    )
)

:: 3. 如需安裝，自動建立 venv 並安裝依賴套件
if "%NEED_INSTALL%"=="1" (
    echo [*] 首次執行或缺少依賴套件，正在準備自動安裝...
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [錯誤] 找不到系統 Python！
        echo 請先安裝 Python 3.10+：https://www.python.org/downloads/
        echo 安裝時請務必勾選 "Add Python to PATH"。
        pause
        exit /b 1
    )

    if not exist "venv\Scripts\python.exe" (
        echo [*] 正在建立虛擬環境 ^(venv^)...
        python -m venv venv
        if errorlevel 1 (
            echo [錯誤] 虛擬環境建立失敗。
            pause
            exit /b 1
        )
    )

    echo [*] 正在安裝必要套件 ^(faster-whisper, opencc, flask^)...
    echo     ^(首次安裝約需 1~3 分鐘，請稍候^)
    venv\Scripts\python.exe -m pip install --upgrade pip -q
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [錯誤] 套件安裝失敗，請檢查網路連線後重試。
        pause
        exit /b 1
    )
    echo [OK] 環境安裝完成！即將自動啟動系統...
    echo.
) else (
    echo [OK] 環境檢查通過，直接啟動系統...
)

:: 4. 啟動應用程式
venv\Scripts\python.exe app.py
pause
