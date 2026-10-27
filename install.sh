#!/bin/bash
echo "======================================"
echo "  Whisper 逐字稿系統 - 安裝程式"
echo "======================================"

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "[✗] 找不到 Python3，請先安裝 Python 3.10+"
    exit 1
fi

echo "[✓] Python 版本：$(python3 --version)"

# 建立虛擬環境
echo ""
echo "[*] 建立虛擬環境..."
python3 -m venv venv
source venv/bin/activate

# 安裝套件
echo "[*] 安裝必要套件（第一次需要幾分鐘）..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "[✓] 安裝完成！"
echo ""
echo "  執行以下指令啟動系統："
echo "  ./start.sh"
echo ""
