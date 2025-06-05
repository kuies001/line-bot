# LINE 機器人

本專案使用 Docker Compose 建立兩個服務：`line_webhook` 與 `html2img`。前者為 Flask 實作的 LINE Bot Webhook，後者則是 Node.js 應用，負責將 HTML 轉換為圖片，供機器人回覆使用。

## 功能特色

- **盤子指令**：輸入「盤子」可查詢台股大盤指數、台積電股價，同時回傳高雄天氣與 AQI 相關資訊。如果為交易日，還會附上分時走勢圖與天氣圖卡。
- **新聞指令**：輸入「新聞」會擷取自由時報政治新聞 (最新三則)。
- **搜尋整合**：輸入「哥哥查 XXX」或「哥哥找 XXX」時，機器人會利用 Playwright 執行 Google 搜尋，再透過 LLM 產生摘要回覆。
- **聊天模式**：訊息以「哥哥」開頭時，透過 OpenRouter (OpenAI API 相容) 與使用者聊天，對話歷史每日備份。
- **定時任務**：每日零點會備份對話紀錄並更新 LLM Prompt，並清理 `/shared` 目錄中的圖片檔案。
- **HTML 轉圖片服務**：`html2img` 服務提供 `POST /render` 介面，只要提交包含 `#screenshot-target` 區塊的 HTML，就會回傳生成的圖片檔名。

## 快速開始

1. 準備 `.env` 檔案，設定 LINE 與外部 API 所需的金鑰：
   ```
   LINE_CHANNEL_SECRET=your_line_channel_secret
   LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
   OPENROUTER_API_KEY=your_openrouter_key
   CWA_API_KEY=your_cwa_key           # 氣象資料
   EPA_API_KEY=your_epa_key           # AQI 資料
   LLM_POLLING_INTERVAL_MINUTES=60
   LLM_MAX_HISTORY=20
   AQICN_TOKEN=your_aqicn_token
   ```
   系統預設提示詞位於 `line_webhook/config/global_system_prompt.txt`，可在 `user_prompt_map.json` 針對特定使用者覆寫。
2. 執行 `docker-compose up -d` 啟動兩個服務。
3. 將 LINE Webhook URL 指向 `http://<你的主機>:1111/callback` 即可開始使用。

## 目錄結構

- `line_webhook/`：主要的 Python 程式碼與 Dockerfile，處理 LINE 訊息事件。
- `html2img/`：Node.js 伺服器，使用 Puppeteer 截取 HTML 畫面成圖片。
- `docker-compose.yml`：定義兩個服務的建置方式與共享資料夾。

## 常用指令

- `盤子`：取得台股行情、天氣與 AQI。
- `新聞`：取得自由時報政治新聞摘要。
- `哥哥查 <關鍵字>` / `哥哥找 <關鍵字>`：網路搜尋並由 LLM 彙整結果。
- `哥哥<訊息>`：與機器人聊天。

## 授權

本專案採用 MIT License 釋出。
