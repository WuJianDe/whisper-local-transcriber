# 🎙️ Whisper 本地語音轉逐字稿系統

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Engine: faster-whisper](https://img.shields.io/badge/Engine-faster--whisper%20(CTranslate2)-6C8FFF)](https://github.com/SYSTRAN/faster-whisper)
[![Flask](https://img.shields.io/badge/Backend-Flask-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-34D399.svg)](https://opensource.org/licenses/MIT)

一套基於 **Flask + `faster-whisper` (CTranslate2)** 打造的現代化本地端 AI 語音轉文字（STT）Web 系統。  
**100% 免費、免 API Key、完全在本地離線運作**，保障會議錄音、訪談與課程音訊的絕對隱私，同時提供比原版 OpenAI Whisper 快 **4～6 倍**的轉錄速度與針對繁體中文的深度調校。

---

## ✨ 核心特色

- 🚀 **極速推理引擎 (`faster-whisper`)**
  - 底層採用 CTranslate2 加速架構，記憶體佔用減少 50% 以上。
  - **硬體自動偵測**：有 NVIDIA GPU 時自動啟用 `CUDA + float16` 加速；無獨顯時自動啟用 CPU `int8` 量化加速。
  - **內建 PyAV 解碼**：開箱即用，無須額外手動配置系統端 `ffmpeg` 環境變數。
- 🔇 **Silero VAD 語音活動偵測 + 防幻覺機制**
  - 自動濾除超過 500ms 的空白靜音區段，大幅加快長音訊處理速度。
  - 結合解碼閥值調校與後處理過濾，有效消除傳統 Whisper 在無聲處常見的「謝謝觀看」、「字幕由...提供」等幻覺（Hallucination）與無限重複鬼打牆。
- ✂️ **智慧靜音切段 (Silence-Aware Chunking)**
  - 長音訊自動依指定分鐘數（如每 10 分鐘）切分儲存獨立 TXT 檔。
  - **不斷句演算法**：在目標切點前後 ±15 秒視窗內自動計算音訊能量均方根（RMS），精準尋找講者**換氣停頓的最低音量處**下刀，確保語意完整不截斷。
- 🇹🇼 **繁體中文深度優化**
  - **自動引導詞 + 跨段上下文銜接**：自動帶入台灣繁體標點引導，並將前一段結尾文字（180 字）動態串接為下一段的 `initial_prompt`，確保長篇錄音前後專有名詞一致。
  - **OpenCC (`s2twp`) 轉換**：自動將模型偶爾產出的簡體字與詞彙轉為台灣繁體慣用字。
- 🖥️ **直覺現代的深色系 Web UI**
  - 拖曳上傳、即時進度條、已辨識字數（支援中/日/韓字元與英文單字混合統計）與耗時監控。
  - **秒級即時中止**：逐句（Segment-level）檢查中止訊號，點擊「停止辨識」1～2 秒內立即停下並保留已完成的部分逐字稿。
  - **一鍵 AI 整理**：內建「複製整理用 Prompt」按鈕，一鍵複製帶指令的逐字稿貼至 ChatGPT / Claude / Gemini 進行潤稿分段。

---

## 📊 支援模型一覽

首次選擇某個模型進行辨識時，系統會自動從 Hugging Face 下載權重並快取於本機，後續皆可完全離線執行：

| 模型 ID | 模型名稱 | 檔案大小 | 速度 | 準確率 | 適用情境與建議 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `tiny` | **Tiny** | ~75 MB | ⚡⚡⚡⚡⚡ | ★★☆☆☆ | 快速測試環境或極短語音備忘 |
| `base` | **Base** | ~142 MB | ⚡⚡⚡⚡☆ | ★★★☆☆ | 音質清晰、無專業術語的一般對話 |
| `small` | **Small** *(預設)* | ~466 MB | ⚡⚡⚡☆☆ | ★★★★☆ | **日常首選**，速度與準確率的最佳平衡點 |
| `medium` | **Medium** | ~1.5 GB | ⚡⚡☆☆☆ | ★★★★☆ | 傳統高精準度模型，適合重要訪談 |
| `turbo` | **Turbo (`large-v3-turbo`)** 🔥 | ~1.5 GB | ⚡⚡⚡☆☆ | ★★★★★ | **強烈推薦**！逼近 Large 的頂尖準確率，但速度快上數倍 |
| `large` | **Large** | ~3.0 GB | ⚡☆☆☆☆ | ★★★★★ | 最高精度、速度最慢，適合多口音或吵雜環境 |

- **支援音訊格式**：`mp3`、`wav`、`m4a`、`ogg`、`flac`、`webm`、`mp4`（單檔上限 **500 MB**）
- **支援語言**：中文（`zh`）、英文（`en`）、日文（`ja`）、韓文（`ko`）、自動偵測（`auto`）

---

## 🛠️ 快速開始

### 1. 環境需求
- 作業系統：Windows 10/11、macOS 或 Linux
- **Python 3.10 或以上版本**（Windows 安裝時請勾選 `Add Python to PATH`）

### 2. 一鍵智慧安裝與啟動

本專案將「環境檢查、套件安裝、啟動伺服器与自動開啟瀏覽器」整合為單一入口，**只需執行 `start-windows.bat`（或 `./start-mac-linux.sh`）**：
- **首次執行（或環境缺件）**：自動建立 `venv` 虛擬環境並安裝所有依賴套件，安裝完成後**自動啟動並開啟網頁介面**。
- **後續執行**：偵測到環境已就緒，**0 秒跳過安裝直接啟動**！

#### Windows
直接雙擊執行 **`start-windows.bat`**（或在終端機輸入）：
```bat
start-windows.bat
```

#### macOS / Linux
```bash
chmod +x start-mac-linux.sh
./start-mac-linux.sh
```

啟動後系統會自動打開瀏覽器前往 👉 **`http://127.0.0.1:5000`**。

---

## 💡 使用技巧（如何讓辨識更準確？）

1. **善用「專有名詞提示（Initial Prompt）」**：
   如果錄音包含特定領域詞彙、人名、公司名或中英夾雜術語，請在左側「專有名詞提示」欄位輸入背景說明與關鍵字，例如：
   > `這是一場軟體架構週會，包含：微服務、Kubernetes、Redis 快取、林協理、張工程師`
2. **長錄音分段保存**：
   3 小時的錄音建議設定為「每 10 分鐘」儲存一個 TXT，每完成一段就會即時寫入 `output/` 資料夾，即使中途斷電或手動按下「停止辨識」，已完成的段落也完整保留。
3. **不切段模式**：
   若短音訊只需要單一完整檔案，將切段選項設為 **「不切段（只存完整版）」**（`chunk_minutes = 999`）即可。

---

## 🔌 API 端點規格

本系統亦提供結構化 JSON API，方便與其他自動化腳本整合：

| 方法 | 路徑 | 說明 |
| :---: | :--- | :--- |
| `GET` | `/` | 載入 Web 操作介面 |
| `GET` | `/models` | 取得支援的模型目錄清單 |
| `POST` | `/transcribe` | 上傳音訊並執行轉錄（`multipart/form-data`：`audio`, `model`, `language`, `chunk_minutes`, `initial_prompt`, `job_id`） |
| `GET` | `/jobs/<job_id>` | 查詢指定任務的即時進度、已處理段數、耗時與字數 |
| `POST` | `/cancel` | 傳入 `{"job_id": "..."}` 請求中止正在執行的任務 |
| `GET` | `/outputs/<filename>` | 下載 `output/` 資料夾內產生的 `.txt` 逐字稿檔案 |

---

## ⚙️ 環境變數設定

預設僅綁定本機 `127.0.0.1:5000` 以確保安全性。如需開放區網內其他裝置存取或變更連接埠，可透過環境變數調整：

```bash
# Windows (PowerShell)
$env:WHISPER_HOST="0.0.0.0"
$env:WHISPER_PORT="8080"
python app.py

# macOS / Linux
WHISPER_HOST=0.0.0.0 WHISPER_PORT=8080 python3 app.py
```

---

## 📂 專案結構與測試

```text
whisper-local-transcriber/
├── app.py               # Flask 後端服務、faster-whisper 轉譯核心、智慧靜音切段與防幻覺處理
├── requirements.txt     # Python 依賴套件清單 (faster-whisper, opencc, flask)
├── static/
│   └── index.html       # 單頁式深色系 Web 前端介面
├── tests/
│   └── test_app.py      # Pytest 自動化單元測試
├── output/              # 轉錄產出的分段與完整 TXT 存放目錄 (已加入 .gitignore)
└── start-windows.bat / start-mac-linux.sh      # 智慧一鍵安裝與啟動腳本（自動偵測環境、安裝依賴並開啟瀏覽器）
```

執行單元測試：
```bash
pytest -q
```
