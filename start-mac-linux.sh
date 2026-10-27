#!/bin/bash
cd "$(dirname "$0")"

echo "===================================================="
echo "  🎙️  Whisper 本地語音轉逐字稿系統 - 智慧啟動器"
echo "===================================================="

NEED_INSTALL=0

# 1. 檢查虛擬環境與 Python 是否可用
if [ ! -x "venv/bin/python" ]; then
    NEED_INSTALL=1
else
    if ! venv/bin/python -c "import sys" &> /dev/null; then
        echo "[!] 偵測到舊的虛擬環境已失效，準備重新建立..."
        rm -rf venv
        NEED_INSTALL=1
    fi
fi

# 2. 檢查核心套件是否已安裝
if [ "$NEED_INSTALL" -eq 0 ]; then
    if ! venv/bin/python -c "import faster_whisper, opencc, flask" &> /dev/null; then
        NEED_INSTALL=1
    fi
fi

# 3. 自動安裝流程
if [ "$NEED_INSTALL" -eq 1 ]; then
    echo "[*] 首次執行或缺少依賴套件，正在準備自動安裝..."
    if ! command -v python3 &> /dev/null; then
        echo "[✗] 找不到 Python3，請先安裝 Python 3.10+"
        exit 1
    fi

    if [ ! -x "venv/bin/python" ]; then
        echo "[*] 正在建立虛擬環境 (venv)..."
        python3 -m venv venv || { echo "[✗] 虛擬環境建立失敗"; exit 1; }
    fi

    echo "[*] 正在安裝必要套件 (faster-whisper, opencc, flask)..."
    venv/bin/python -m pip install --upgrade pip -q
    venv/bin/python -m pip install -r requirements.txt || { echo "[✗] 套件安裝失敗"; exit 1; }
    echo "[✓] 環境安裝完成！即將自動啟動系統..."
    echo ""
else
    echo "[✓] 環境檢查通過，直接啟動系統..."
fi

# 4. 啟動應用程式
venv/bin/python app.py
