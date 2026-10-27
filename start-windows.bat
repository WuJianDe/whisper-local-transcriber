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

:: 3. 如需安裝，自動尋找系統可用的 Python 並建立 venv
if "%NEED_INSTALL%"=="1" (
    echo [*] 首次執行或缺少依賴套件，正在準備自動安裝...
    set "SYS_PY="

    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "SYS_PY=python"

    if not defined SYS_PY (
        py -3 -c "import sys" >nul 2>&1
        if not errorlevel 1 set "SYS_PY=py -3"
    )

    if not defined SYS_PY (
        for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
            if exist "%%D\python.exe" set "SYS_PY="%%D\python.exe""
        )
    )

    if not defined SYS_PY (
        echo.
        echo [!] 系統尚未安裝可用的 Python 3.10+ 環境（或舊版 Python 已被移除）。
        where winget >nul 2>&1
        if not errorlevel 1 (
            echo [*] 偵測到 Windows 套件管理員 ^(winget^)，正在為您自動下載並安裝 Python 3.12...
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
                if exist "%%D\python.exe" set "SYS_PY="%%D\python.exe""
            )
        )
    )

    if not defined SYS_PY (
        echo [錯誤] 找不到可用的 Python 環境！
        echo 請前往 https://www.python.org/downloads/ 下載安裝 Python 3.11 或 3.12
        echo 安裝時請務必勾選底部的 "Add python.exe to PATH"。
        pause
        exit /b 1
    )

    if not exist "venv\Scripts\python.exe" (
        echo [*] 正在建立虛擬環境 ^(venv^)...
        %SYS_PY% -m venv venv
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
