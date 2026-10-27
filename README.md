# Whisper 本地轉錄系統 (faster-whisper 加速版)

以 Flask + `faster-whisper` (CTranslate2) 建立的本地語音轉文字工具，提供 Web 介面上傳音訊、即時進度查詢、秒級中止任務，並輸出完整稿與智慧靜音分段文字檔。完全免費、本地離線執行。

## 系統特色與優化
- **高速轉譯引擎 (`faster-whisper`)**：相較原版 Whisper 速度提升 4~6 倍、記憶體佔用減半（GPU 自動啟用 `float16`，CPU 自動啟用 `int8` 量化加速）。
- **內建 Silero VAD 靜音過濾**：自動跳過無聲空白片段，大幅減少「謝謝觀看」等背景幻覺與重複鬼打牆。
- **智慧靜音切段 (Silence-aware Chunking)**：在目標分段點前後自動尋找音量最低的換氣停頓點下刀，不切斷句子。
- **繁體中文強化**：內建繁體中文標點引導詞，並整合 `OpenCC (s2twp)` 自動轉換簡體字與台灣慣用詞；跨分段自動銜接上下文提示。
- **支援檔案與模型**：
  - 上傳上限 500MB，支援 `mp3`、`wav`、`m4a`、`ogg`、`flac`、`webm`、`mp4`。
  - 模型：`tiny`、`base`、`small`、`medium`、`turbo` (`large-v3-turbo`)、`large`。
  - 語言：`auto`、`zh`、`en`、`ja`、`ko`。

## 必要環境

- Python 3.10+
- `pip`
- 首次安裝與首次使用模型時需連網下載套件與模型權重

安裝腳本會根據 `requirements.txt` 自動安裝：
- `faster-whisper`
- `opencc-python-reimplemented`
- `flask`

## 安裝與啟動

### Windows

```bat
install.bat
start.bat
```

### Linux / macOS

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

啟動後開啟：`http://127.0.0.1:5000`

## 補充行為

- `chunk_minutes = 999` 時，不輸出分段檔，只輸出完整檔（或中止部分檔）。
- 前端每 3 秒輪詢 `/jobs/<job_id>` 即時更新進度與已辨識字數，並支援「停止辨識」（逐句即時中斷）、逐字稿複製與各分段檔案獨立下載（`GET /outputs/<filename>`）。
- 預設僅綁定本機 `127.0.0.1:5000`，可透過環境變數 `WHISPER_HOST=0.0.0.0` 與 `WHISPER_PORT` 自訂。