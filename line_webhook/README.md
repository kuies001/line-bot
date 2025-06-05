# LINE Webhook 服務程式說明

此目錄包含三支與 LINE Bot 相關的 Python 程式，分別負責主程式、股市資料擷取以及每日設定檔更新。

## 1. `line_webhook_app.py`

主要的 Flask 應用程式，提供 LINE Webhook 介面並串接多項功能：

- 透過 `WebhookHandler` 處理文字訊息，依指令回傳股票、天氣、AQI 及新聞等資訊。
- 與 OpenRouter 相容的 LLM 服務互動，實作聊天與搜尋摘要功能。
- 使用 `schedule` 及背景執行緒每日歸檔對話紀錄、更新 Prompt 並清理圖片目錄。
- 提供 `/static/<filename>` 路由讓 LINE Bot 能回傳由 `html2img` 服務產生的圖片。

程式會定期載入 `config/global_system_prompt.txt` 的內容，並根據 `user_prompt_map.json` 提供的設定對不同使用者套用客製化提示，所有歷史紀錄也存放在 `config/` 目錄。

## 2. `append_twse_tick.py`

定期抓取台股加權指數即時行情，將資料追加至當日 CSV：

- 每兩秒向 `https://mis.twse.com.tw/stock/api/getStockInfo.jsp` 取得大盤指數與時間。
- 避免重複寫入相同時間戳的資料。
- 收盤後（13:30）自動結束，並將七天前的舊 CSV 以 gzip 壓縮存入 `archive/`。

此腳本可搭配排程工具於交易日時執行，供 `plot_twse_intraday.py` 繪製分時圖使用。

## 3. `daily_rollover.py`

每日更新 LLM system prompt 的輕量工具：

- 讀取 `config/global_system_prompt.txt`，複製到 `LLM_HISTORY_FILE` 所指的覆寫檔。
- 先將前一天的覆寫檔重新命名（帶入日期）備份，以保留歷史紀錄。

可配合排程（例如 `cron` 或 `schedule`）在每日零點執行，使聊天機器人持續使用最新的提示詞。

## 執行環境

- Python 3.10 以上
- 相關依賴請參考 `requirements.txt`
- 執行前需準備 `.env` 檔案設定 LINE 與外部 API 金鑰

