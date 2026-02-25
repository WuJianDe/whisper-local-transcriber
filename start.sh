#!/bin/bash
cd "$(dirname "$0")"

# 啟動虛擬環境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "======================================"
echo "  🎙️  Whisper 逐字稿系統"
echo "======================================"
echo "  網址：http://localhost:5000"
echo "  按 Ctrl+C 停止"
echo "======================================"
echo ""

python3 app.py
