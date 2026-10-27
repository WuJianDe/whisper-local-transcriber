# Whisper 本地轉錄系統

以 Flask + OpenAI Whisper 建立的本地語音轉文字工具，提供 Web 介面上傳音訊、即時進度查詢、可中止任務，並輸出完整稿與分段稿文字檔。

## 系統功能
- 本地 Web 介面：`GET /` 提供前端操作頁。
- 僅允許 1 個並行任務。
- 任務狀態保存 1 小時，逾時會清理。
- 檔案大小上限 500MB。
- 支援上傳格式：`mp3`、`wav`、`m4a`、`ogg`、`flac`、`webm`、`mp4`。
- 允許模型：`tiny`、`base`、`small`、`medium`、`large`。
- 允許語言：`auto`、`zh`、`en`、`ja`、`ko`。
- 支援 `initial_prompt`（專有名詞提示）與 `chunk_minutes`（1..999）。

## 必要環境

- Python 3.10+
- `pip`
- 首次安裝需可連網（下載套件與模型）

安裝腳本會安裝：

- `openai-whisper`
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

啟動後開啟：`http://localhost:5000`

## 補充行為

- `chunk_minutes = 999` 時，不輸出分段檔，只輸出完整檔（或中止部分檔）。
- 前端會每 3 秒輪詢 `/jobs/<job_id>` 即時更新進度與已辨識字數，並支援「停止辨識」、逐字稿複製與各分段檔案獨立下載（`GET /outputs/<filename>`）。
- 預設僅綁定本機 `127.0.0.1:5000`，可透過環境變數 `WHISPER_HOST=0.0.0.0` 與 `WHISPER_PORT` 自訂。
- 自動偵測 CUDA GPU 並啟用 `fp16` 加速；跨分段自動銜接前段結尾文字作為上下文提示。
