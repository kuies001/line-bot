# line_webhook_app.py
import os
import sys
import shutil
import json # 引入 json 處理 API 回應
import requests # 引入 requests 發送 HTTP 請求
import urllib.parse
import re
from dotenv import load_dotenv
load_dotenv()
import subprocess
from flask import Flask, request, abort
from flask import send_from_directory
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    TextMessage,
    ImageMessage,
    ReplyMessageRequest,
    PushMessageRequest,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from bs4 import BeautifulSoup
import re
import yfinance as yf
from datetime import datetime, timedelta
this_year = datetime.now().year
import pytz
import time # 引入 time 模組，用於 sleep
import random
import threading # 引入 threading 模組，用於背景執行緒
from typing import Optional
import schedule # 引入 schedule 模組，用於定時任務
import openai # 用于 OpenRouter
import feedparser
import mplfinance as mpf
import matplotlib.pyplot as plt
import pandas as pd

# 共享目錄路徑，可透過環境變數 SHARED_DIR 覆寫
SHARED_DIR = os.getenv('SHARED_DIR', '/shared')

# 設定台灣時區
tz = pytz.timezone("Asia/Taipei")

# 從 .env 載入金鑰 變數
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
AQICN_TOKEN = os.getenv("AQICN_TOKEN")
LLM_PROMPT_FILE = os.getenv('LLM_PROMPT_FILE')

# 定時輪詢的間隔 (分鐘)
LLM_POLLING_INTERVAL_MINUTES = int(os.getenv('LLM_POLLING_INTERVAL_MINUTES', '60')) # 預設 30 分鐘


# 新增氣象和 AQI 的 API Key
CWA_API_KEY = os.getenv('CWA_API_KEY') # CWA 氣象 API 金鑰
EPA_API_KEY = os.getenv('EPA_API_KEY') # EPA AQI API 金鑰


# LLM的prompt檔案
load_dotenv()
PROMPT_FILE  = os.getenv('LLM_PROMPT_FILE')      # /app/config/llm_config.json
# 路徑存放每日覆寫的 Prompt 版本，和 daily_rollover.py 使用的環境變數名稱一致
OVERRIDE_FILE = os.getenv('LLM_HISTORY_FILE', '/app/config/llm_config_old.json')
# 對話歷史檔 (預設值會放在 /app/config/history_default.json)
HISTORY_FILE = os.getenv('HISTORY_FILE', '/app/config/history_default.json')

def load_system_prompt():  
    with open(OVERRIDE_FILE, 'r', encoding='utf-8') as f:  
        return f.read()  

def rollover_prompt():
    today = datetime.today().strftime('%Y-%m-%d')
    dst = OVERRIDE_FILE.replace('llm_config_old.json', f'llm_config_old_{today}.json')
    if os.path.exists(OVERRIDE_FILE):
        shutil.move(OVERRIDE_FILE, dst)
    shutil.copy(PROMPT_FILE, OVERRIDE_FILE)
    print(f'rollover prompt to {dst}')

def archive_html2img_output():
    """Archive SHARED_DIR into dated tar.gz and clean the folder."""
    today = datetime.now(tz).strftime('%Y-%m-%d')
    src_dir = SHARED_DIR
    dst_root = os.path.join(SHARED_DIR, 'archive')
    os.makedirs(dst_root, exist_ok=True)
    archive_base = os.path.join(dst_root, f'html2img_{today}')
    try:
        shutil.make_archive(archive_base, 'gztar', src_dir)
        for name in os.listdir(src_dir):
            if name == 'archive':
                continue
            path = os.path.join(src_dir, name)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)
            except Exception as e:
                print(f'WARN: Failed to remove {path}: {e}', file=sys.stderr)
        print(f'archived html2img_output to {archive_base}.tar.gz', file=sys.stderr)
    except Exception as e:
        print(f'ERROR: archive_html2img_output failed: {e}', file=sys.stderr)

schedule.every().day.at("00:00").do(rollover_prompt)
schedule.every().day.at("00:00").do(archive_html2img_output)

def run_scheduler():  
    while True:  
        schedule.run_pending()  
        time.sleep(30)  

threading.Thread(target=run_scheduler, daemon=True).start()

# ====== DEBUG 打印金鑰狀態 ======
print(f"DEBUG: Loaded LINE_CHANNEL_SECRET: '{LINE_CHANNEL_SECRET[:8] if LINE_CHANNEL_SECRET else 'None'}'...", file=sys.stderr)
print(f"DEBUG: Loaded OPENROUTER_API_KEY: '{OPENROUTER_API_KEY[:8] if OPENROUTER_API_KEY else 'None'}'...", file=sys.stderr)
print(f"DEBUG: LLM_PROMPT_FILE: '{LLM_PROMPT_FILE}'...", file=sys.stderr)
print(f"DEBUG: LLM_POLLING_INTERVAL_MINUTES: {LLM_POLLING_INTERVAL_MINUTES} minutes...", file=sys.stderr)
if CWA_API_KEY:
    print(f"DEBUG: Loaded CWA_API_KEY (exists)", file=sys.stderr)
else:
    print(f"DEBUG: CWA_API_KEY not set.", file=sys.stderr)
if EPA_API_KEY:
    print(f"DEBUG: Loaded EPA_API_KEY (exists)", file=sys.stderr)
else:
    print(f"DEBUG: EPA_API_KEY not set.", file=sys.stderr)
# ===============================

# 確保 LINE Secret 已載入
if not LINE_CHANNEL_SECRET:
    print("錯誤：請在 .env 檔案中設定 LINE_CHANNEL_SECRET", file=sys.stderr)
    sys.exit(1)

# 警告其他金鑰狀態
if not LINE_CHANNEL_ACCESS_TOKEN:
    print("警告：請在 .env 檔案中設定 LINE_CHANNEL_ACCESS_TOKEN (用於發送訊息)", file=sys.stderr)
if not OPENROUTER_API_KEY:
    print("警告：請在 .env 檔案中設定 OPENROUTER_API_KEY，LLM 聊天功能將不可用。", file=sys.stderr)
if not CWA_API_KEY:
    print("警告：請在 .env 檔案中設定 CWA_API_KEY，氣象查詢功能將不可用。", file=sys.stderr)
if not EPA_API_KEY:
    print("警告：請在 .env 檔案中設定 EPA_API_KEY，AQI 查詢功能將不可用。", file=sys.stderr)


# ====== 初始化 Flask App ======
app = Flask(__name__, static_folder=SHARED_DIR, static_url_path="/static")

# =====Flask 靜態檔案服務的路由=====
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(SHARED_DIR, filename)

# 初始化 LINE Messaging API 客戶端和 Webhook 處理器
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === 初始化 OpenAI 客戶端，指向 OpenRouter ===
client_openrouter = None
if OPENROUTER_API_KEY:
    try:
        client_openrouter = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY
        )
        print("INFO: OpenAI client initialized for OpenRouter.", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Failed to initialize OpenAI client for OpenRouter: {e}", file=sys.stderr)
        client_openrouter = None

# === 載入 LLM System Prompt 及定時重載機制相關變數 ===
LLM_SYSTEM_PROMPT = None # 初始化 Prompt 變數
last_modified_time = None # 初始化記錄檔案修改時間的變數

# =====數字轉 emoji 讓數值視覺化=====
def to_emoji_number(num: int) -> str:
    emoji_digits = {
        "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
        "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣",
        ".": ".", "%": "%"
    }
    return ''.join(emoji_digits.get(c, c) for c in str(num))

# =====天氣輔助函式=====
def get_aqi_emoji(aqi_value: int) -> str:
    if aqi_value <= 50:
        return "🟢"
    elif aqi_value <= 100:
        return "🟡"
    elif aqi_value <= 150:
        return "🟠"
    elif aqi_value <= 200:
        return "🔴"
    elif aqi_value <= 300:
        return "🟣"
    else:
        return "⚫"

def get_rain_emoji(pop: int) -> str:
    if pop < 20:
        return "☀️"
    elif pop < 50:
        return "🌤"
    elif pop < 80:
        return "🌧"
    else:
        return "⛈"

def get_temp_emoji(max_temp: int) -> str:
    if max_temp <= 18:
        return "❄️"
    elif max_temp <= 27:
        return "😊"
    elif max_temp <= 32:
        return "🥵"
    else:
        return "🔥"
        
# ===== AQI判斷函數 =====
def get_aqi_comment(aqi_value):
    if aqi_value is None:
        return ""
    try:
        aqi = int(aqi_value)
    except:
        return ""
    if aqi <= 50:
        return "空氣良好，適合學凱翔去跑步"
    elif aqi <= 80:
        return "普通，跟廣廣一樣普通"
    elif aqi <= 100:
        return "略差，外出建議戴口罩"
    elif aqi <= 140:
        return "不佳，戴口罩或是少出門"
    else:
        return "地球要毀滅了，準備迎接第三次衝擊"

# ====== 定義 Helper 函數 (確保在 handle_message 定義之前) ======

def load_llm_prompt():
    """從檔案載入 LLM System Prompt"""
    # === 新增 Debug 打印：進入函式 ===
    print("DEBUG: Entered load_llm_prompt function.", file=sys.stderr)
    # =================================

    global LLM_SYSTEM_PROMPT, last_modified_time
    if not LLM_PROMPT_FILE:
        # 如果沒有設定檔案路徑，則使用預設 Prompt，並不再嘗試載入
        if LLM_SYSTEM_PROMPT is None: # 只有第一次未設定時才打印警告
             print("WARNING: LLM_PROMPT_FILE environment variable not set. Using default LLM system prompt.", file=sys.stderr)
             LLM_SYSTEM_PROMPT = "你是一個有禮貌的 LINE 聊天機器人，請使用繁體中文回覆。"
        return # 不進行檔案操作

    if not os.path.exists(LLM_PROMPT_FILE):
         # 如果檔案不存在，只有第一次或檔案消失時才打印警告
         if LLM_SYSTEM_PROMPT is None or last_modified_time is not None: # 如果 Prompt 是 None 或之前成功載入過 (檔案消失)
              print(f"WARNING: LLM prompt file not found at {LLM_PROMPT_FILE}. Using default LLM system prompt or keeping old one.", file=sys.stderr)
              # 檔案不存在，如果之前成功載入過，則保留舊的；如果沒有，則使用預設。
              if LLM_SYSTEM_PROMPT is None:
                   LLM_SYSTEM_PROMPT = "你是一個有禮貌的 LINE 聊天機器人，請使用繁體中文回覆。"
              last_modified_time = None # Reset modified time if file disappears
         return # 不進行檔案操作

    try:
        current_modified_time = os.path.getmtime(LLM_PROMPT_FILE)
        # 只有當檔案修改時間比上次載入時新，或者這是第一次載入時才重新讀取
        if last_modified_time is None or current_modified_time > last_modified_time:
            print(f"INFO: Loading LLM system prompt from {LLM_PROMPT_FILE} (Last modified: {datetime.fromtimestamp(current_modified_time).strftime('%Y-%m-%d %H:%M:%S')})...", file=sys.stderr) # 格式化時間打印
            with open(LLM_PROMPT_FILE, 'r', encoding='utf-8') as f:
                prompt_config = json.load(f)
                new_prompt = prompt_config.get("system_prompt")

                if new_prompt:
                    LLM_SYSTEM_PROMPT = new_prompt
                    last_modified_time = current_modified_time # 更新修改時間
                    print(f"INFO: Successfully loaded new LLM system prompt (length: {len(LLM_SYSTEM_PROMPT)}).", file=sys.stderr)
                else:
                    print(f"WARNING: 'system_prompt' key not found or empty in {LLM_PROMPT_FILE}. Keeping old prompt or using default.", file=sys.stderr)
                    # 如果檔案存在但內容不正確，如果之前沒 Prompt 則使用預設
                    if LLM_SYSTEM_PROMPT is None:
                         LLM_SYSTEM_PROMPT = "你是一個有禮貌的 LINE 聊天機器人，請使用繁體中文回覆。"
                    # 不更新 last_modified_time，這樣下次輪詢時會再次嘗試載入 (直到檔案內容變正確)

    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON from {LLM_PROMPT_FILE}: {e}. Keeping old prompt or using default.", file=sys.stderr)
        # 解析失敗，如果之前沒 Prompt 則使用預設
        if LLM_SYSTEM_PROMPT is None:
             LLM_SYSTEM_PROMPT = "你是一個有禮貌的 LINE 聊天機器人，請使用繁體中文回覆。"
        # 不更新 last_modified_time，這樣下次輪詢時會再次嘗試載入 (直到檔案內容變正確)
    except Exception as e:
        print(f"ERROR: Unexpected error reading LLM prompt file {LLM_PROMPT_FILE}: {e}. Keeping old prompt or using default.", file=sys.stderr)
        # 其他讀取錯誤，如果之前沒 Prompt 則使用預設
        if LLM_SYSTEM_PROMPT is None:
             LLM_SYSTEM_PROMPT = "你是一個有禮貌的 LINE 聊天機器人，請使用繁體中文回覆。"
        # 不更新 last_modified_time


def run_scheduler():
    """運行定時任務排程器"""
    print(f"INFO: LLM prompt file auto-reload scheduler thread started (interval: {LLM_POLLING_INTERVAL_MINUTES} minutes).", file=sys.stderr)
    # 在執行排程器循環之前，先等待一小段時間，避免剛啟動就觸發首次輪詢（首次載入已在前面完成）
    time.sleep(5)
    while True:
        schedule.run_pending()
        time.sleep(1) # 每秒檢查一次排程是否有任務需要運行


# ====== 自由時報政治新聞RSS ======

import feedparser

def get_ltn_politics_news():
    rss_url = "https://news.ltn.com.tw/rss/politics.xml"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return [{"title": "⚠️ 抓不到新聞，可能 RSS 無內容", "time": "", "url": rss_url}]
        
        result = []
        for entry in feed.entries[:3]:
            title = entry.title
            link = entry.link
            published = entry.published if 'published' in entry else "未知時間"
            result.append({"title": title, "time": published, "url": link})
        return result
    except Exception as e:
        return [{"title": f"⚠️ 抓取失敗：{e}", "time": "", "url": rss_url}]

# ====== 通用股票查詢函數 (個別股票) ======
# 保持原樣
def get_stock_price(ticker_symbol: str, display_name: str):
    """
    查詢指定股票代碼的股價，並使用 display_name 顯示，格式為 名稱(代號)。
    根據漲跌添加 emoji 並顯示漲跌百分比。
    """
    if not ticker_symbol:
        return f"❌ 讀取 {display_name} ({ticker_symbol}) 股價失敗：未提供股票代碼"

    # 確保台股代碼有 .TW 後綴
    if not ticker_symbol.endswith('.TW') and ticker_symbol.isdigit():
         full_ticker = f"{ticker_symbol}.TW"
    else:
         full_ticker = ticker_symbol

    print(f"DEBUG: Querying stock ticker: {full_ticker}", file=sys.stderr)

    # 初始化所有可能在報告中使用的變數及預設值
    current_price = None
    previous_close = None
    open_price = None
    day_high = None
    day_low = None

    price_str = "N/A"
    change = None
    change_percent = None
    change_str_formatted = "N/A"
    percent_change_str_formatted = "N/A"
    # === 使用 Unicode 逃逸序列表示預設 emoji ===
    emoji = "\u2194" # Unicode for ↔️ (Left Right Arrow)
    # =========================================

    open_high_low_str = None # 用於儲存開盤/高/低盤的格式化字串

    now = datetime.now(tz)
    formatted_now = now.strftime("%m/%d %H:%M")

    try:
        ticker = yf.Ticker(full_ticker)
        # 嘗試獲取股票基本資訊
        try:
             info = ticker.info
             print(f"DEBUG: Info data keys for {full_ticker}: {list(info.keys()) if info else 'None'}", file=sys.stderr)
             current_price = info.get('currentPrice')
             if current_price is None: current_price = info.get('regularMarketPrice') # 備用價格
             previous_close = info.get('previousClose')
             open_price = info.get('open')
             day_high = info.get('dayHigh')
             day_low = info.get('dayLow')
             print(f"DEBUG: Info data values for {full_ticker}: currentPrice={current_price}, previousClose={previous_close}, open={open_price}, high={day_high}, low={day_low}", file=sys.stderr)
        except Exception as info_e:
             print(f"WARNING: Error fetching info for {full_ticker}: {info_e}", file=sys.stderr)
             info = {} # Ensure info is an empty dict if fetching fails


        # 如果 current_price 無法取得，嘗試從歷史數據獲取最後收盤價
        if current_price is None:
             print(f"DEBUG: currentPrice is None from info for {full_ticker}, trying history.", file=sys.stderr)
             try:
                 # 獲取過去兩天的歷史數據，以確保能取得昨收價或今日開盤前的收盤價
                 hist = ticker.history(period="2d", auto_adjust=False, prepost=False)
                 print(f"DEBUG: History data shape for {full_ticker}: {hist.shape}", file=sys.stderr)
                 if not hist.empty:
                      current_price = hist.iloc[-1]['Close']
                      print(f"DEBUG: Falling back to history last close for {full_ticker}: {current_price}", file=sys.stderr)
                      # 如果 previous_close 也沒有，則嘗試從 history 中獲取前一天的收盤價
                      if previous_close is None and len(hist) > 1:
                           previous_close = hist.iloc[-2]['Close']
                           print(f"DEBUG: Falling back to history second last close for {full_ticker} as previousClose: {previous_close}", file=sys.stderr)
                      elif previous_close is None and len(hist) == 1:
                           # 只有一天的歷史數據，且 info 中沒有 previous_close
                           print(f"DEBUG: Only one day history and no previousClose from info for {full_ticker}. Cannot calculate change.", file=sys.stderr)
                           previous_close = None # 確保 previous_close 是 None 以便不計算漲跌
                 else:
                      print(f"DEBUG: History data is empty for {full_ticker}.", file=sys.stderr)

             except Exception as hist_e:
                 print(f"WARNING: Error fetching history data for {full_ticker}: {hist_e}", file=sys.stderr)


        # 格式化價格，如果 current_price 仍然是 None，price_str 保持 N/A
        if current_price is not None:
             price_str = f"{current_price:.2f}"

        # 計算漲跌和百分比漲跌
        # 只有在 current_price 和 previous_close 都有效且 previous_close 不為 0 時才計算
        if current_price is not None and previous_close is not None and previous_close != 0:
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100
            change_str_formatted = f"{'+' if change >= 0 else ''}{change:.2f}"
            percent_change_str_formatted = f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%"

            # 根據漲跌設置 emoji
            if change > 0:
                 # === 修改：使用 Unicode 逃逸序列表示上漲 emoji ===
                 emoji = "\U0001F4C8" # Unicode for  (Chart Increasing)
                 # =============================================
            elif change < 0:
                 # === 修改：使用 Unicode 逃逸序列表示下跌 emoji ===
                 emoji = "\U0001F4C9" # Unicode for  (Chart Decreasing)
                 # =============================================
            # change == 0 時 emoji 保持預設的 ↔️ (\u2194)

            print(f"DEBUG: Calculated change={change}, change_percent={change_percent}, emoji='{emoji}' for {full_ticker}", file=sys.stderr)
        else:
             # 如果無法計算漲跌，確保相關變數是預設的 N/A 和 ↔️ (\u2194)
             print(f"DEBUG: Cannot calculate change/percent for {full_ticker}: current_price={current_price}, previous_close={previous_close}. Setting N/A and ↔️.", file=sys.stderr)
             change_str_formatted = "N/A"
             percent_change_str_formatted = "N/A"
             # === 無法計算時也使用 Unicode 逃逸序列 ===
             emoji = "\u2194" # Unicode for ↔️
             # =======================================


        # 格式化開盤/高/低盤信息
        # 只有在開高低都有效且合理時才生成這行
        # 即使 price 來自 history，如果 info 有這些盤中數據也可以顯示 (雖然可能不是最新的)
        if open_price is not None and day_high is not None and day_low is not None and day_high > 0 and day_low > 0 and day_high >= day_low:
             open_high_low_str = f"開盤：{open_price:.2f} / 高：{day_high:.2f} / 低：{day_low:.2f}"
        elif open_price is not None and open_price > 0: # 如果只有開盤價
             open_high_low_str = f"開盤：{open_price:.2f}"


        # ====== 構建報告訊息 ======
        # 如果連價格都讀取不到，返回錯誤
        if price_str == "N/A":
             print(f"DEBUG: Final price_str is N/A for {full_ticker}. Returning error report.", file=sys.stderr)
             return f"❌ 讀取 {display_name} ({ticker_symbol}) 股價資訊失敗。"

        # 構建報告字串，使用已經格式化好的變數
        # === 增加更多除錯打印並使用顯式拼接（零寬度空格保留）===
        first_line_base = f"{display_name} ({ticker_symbol})（{formatted_now}）"

        # 打印 emoji 和 base 內容在拼接前
        print(f"DEBUG: Before拼接 {full_ticker}: emoji='{emoji}' (len={len(emoji)}), base='{first_line_base}' (len={len(first_line_base)})", file=sys.stderr)

        # 使用顯式拼接，並在 emoji 後添加零寬度空格 '\u200B'
        first_line_content = emoji + "\u200B" + first_line_base

        report_msg = first_line_content + "\n" + \
                     f"價格：{price_str}\n" + \
                     f"漲跌：{change_str_formatted} ({percent_change_str_formatted})"
        # =====================================================================

        # 如果有開盤/高/低盤信息，則添加
        if open_high_low_str:
             report_msg += f"\n{open_high_low_str}"

        # 檢查構建後的報告字串開頭
        print(f"DEBUG: Final formatted report check for {full_ticker}: Starts with '{report_msg[:min(len(report_msg), 10)]}', full length: {len(report_msg.strip())}", file=sys.stderr)


        return report_msg.strip()

    except Exception as e:
        print(f"DEBUG: Unexpected error in get_stock_price for {full_ticker}: {e}", file=sys.stderr)
        # 錯誤信息也使用 display_name 和原始 ticker
        return f"❌ 讀取 {display_name} ({ticker_symbol}) 股價失敗：{e}"


# ====== 大盤指數查詢函數 ======
# 保持原樣
def get_market_index():
    """
    查詢台股加權指數 (^TWII) 資訊，並根據漲跌添加 emoji 並顯示漲跌百分比。
    """
    ticker_symbol = "^TWII"
    display_name = "台股加權指數" # 大盤的顯示名稱
    print(f"DEBUG: Querying market index: {ticker_symbol}", file=sys.stderr)

    # 初始化所有可能在報告中使用的變數及預設值
    current_price = None
    previous_close = None
    open_price = None
    day_high = None
    day_low = None

    price_str = "N/A"
    change = None
    change_percent = None
    change_str_formatted = "N/A"
    percent_change_str_formatted = "N/A"
    # === 使用 Unicode 逃逸序列表示預設 emoji ===
    emoji = "\u2194" # Unicode for ↔️ (Left Right Arrow)
    # =================================================

    open_high_low_str = None # 用於儲存開盤/高/低盤的格式化字串

    now = datetime.now(tz)
    formatted_now = now.strftime("%m/%d %H:%M")

    try:
        ticker = yf.Ticker(ticker_symbol)
        # 嘗試獲取指數基本資訊
        try:
            info = ticker.info
            print(f"DEBUG: Info data keys for {ticker_symbol}: {list(info.keys()) if info else 'None'}", file=sys.stderr)
            current_price = info.get('currentPrice')
            if current_price is None: current_price = info.get('regularMarketPrice')
            previous_close = info.get('previousClose')
            open_price = info.get('open')
            day_high = info.get('dayHigh')
            day_low = info.get('dayLow')
            print(f"DEBUG: Info data values for {ticker_symbol}: currentPrice={current_price}, previousClose={previous_close}, open={open_price}, high={day_high}, low={day_low}", file=sys.stderr)

        except Exception as info_e:
             print(f"WARNING: Error fetching info for {ticker_symbol}: {info_e}", file=sys.stderr)
             info = {} # Ensure info is an empty dict if fetching fails


        # 如果 current_price 無法取得，嘗試從歷史數據獲取最後收盤價
        if current_price is None:
             print(f"DEBUG: currentPrice is None from info for {ticker_symbol}, trying history.", file=sys.stderr)
             try:
                 hist = ticker.history(period="2d", auto_adjust=False, prepost=False)
                 print(f"DEBUG: History data shape for {ticker_symbol}: {hist.shape}", file=sys.stderr)

                 if not hist.empty:
                      current_price = hist.iloc[-1]['Close']
                      print(f"DEBUG: Falling back to history last close for {ticker_symbol}: {current_price}", file=sys.stderr)
                      if previous_close is None and len(hist) > 1:
                           previous_close = hist.iloc[-2]['Close']
                           print(f"DEBUG: Falling back to history second last close for {ticker_symbol} as previousClose: {previous_close}", file=sys.stderr)
                      elif previous_close is None and len(hist) == 1:
                           print(f"DEBUG: Only one day history and no previousClose from info for {ticker_symbol}. Cannot calculate change.", file=sys.stderr)
                           previous_close = None

                 else:
                      print(f"DEBUG: History data is empty for {ticker_symbol}.", file=sys.stderr)

             except Exception as hist_e:
                 print(f"WARNING: Error fetching history data for {ticker_symbol}: {hist_e}", file=sys.stderr)


        # 格式化價格，如果 current_price 仍然是 None，price_str 保持 N/A
        if current_price is not None:
             price_str = f"{current_price:.2f}"

        # 計算漲跌和百分比漲跌
        # 只有在 current_price 和 previous_close 都有效且 previous_close 不為 0 時才計算
        if current_price is not None and previous_close is not None and previous_close != 0:
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100
            change_str_formatted = f"{'+' if change >= 0 else ''}{change:.2f}"
            percent_change_str_formatted = f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%"

            # 根據漲跌設置 emoji
            if change > 0:
                # === 修改：使用 Unicode 逃逸序列表示上漲 emoji ===
                emoji = "\U0001F4C8" # Unicode for 
                # =============================================
            elif change < 0:
                # === 修改：使用 Unicode 逃逸序列表示下跌 emoji ===
                emoji = "\U0001F4C9" # Unicode for 
                # =============================================
            # change == 0 時 emoji 保持預設的 ↔️ (\u2194)

            print(f"DEBUG: Calculated change={change}, change_percent={change_percent}, emoji='{emoji}' for {ticker_symbol}", file=sys.stderr)
        else:
             # 如果無法計算漲跌，確保相關變數是預設的 N/A 和 ↔️ (\u2194)
             print(f"DEBUG: Cannot calculate change/percent for {ticker_symbol}: current_price={current_price}, previous_close={previous_close}. Setting N/A and ↔️.", file=sys.stderr)
             change_str_formatted = "N/A"
             percent_change_str_formatted = "N/A"
             # === 無法計算時也使用 Unicode 逃逸序列 ===
             emoji = "\u2194" # Unicode for ↔️
             # =======================================


        # 格式化開盤/高/低盤信息
        # 只有在開高低都有效且合理時才生成這行
        if open_price is not None and day_high is not None and day_low is not None and day_high > 0 and day_low > 0 and day_high >= day_low:
             open_high_low_str = f"開盤：{open_price:.2f} / 高：{day_high:.2f} / 低：{day_low:.2f}"
        elif open_price is not None and open_price > 0: # 如果只有開盤價
             open_high_low_str = f"開盤：{open_price:.2f}"


        # ====== 構建報告訊息 ======
        # 如果連價格都讀取不到，返回錯誤
        if price_str == "N/A":
             print(f"DEBUG: Final price_str is N/A for {ticker_symbol}. Returning error report.", file=sys.stderr)
             return f"❌ 無法取得 {display_name} 資訊。"


        # 構建報告字串，使用已經格式化好的變數
        # === 增加更多除錯打印並使用顯式拼接（零寬度空格保留）===
        first_line_base = f"{display_name}（{formatted_now}）"

        # 打印 emoji 和 base 內容在拼接前
        print(f"DEBUG: Before拼接 {ticker_symbol}: emoji='{emoji}' (len={len(emoji)}), base='{first_line_base}' (len={len(first_line_base)})", file=sys.stderr)

        # 使用顯式拼接，並在 emoji 後添加零寬度空格 '\u200B'
        first_line_content = emoji + "\u200B" + first_line_base

        report_msg = first_line_content + "\n" + \
                     f"指數：{price_str}\n" + \
                     f"漲跌：{change_str_formatted} ({percent_change_str_formatted})"
        # =====================================================================

        # 如果有開盤/高/低盤信息，則添加
        if open_high_low_str:
             report_msg += f"\n{open_high_low_str}"

        # 檢查構建後的報告字串開頭
        print(f"DEBUG: Final formatted report check for {ticker_symbol}: Starts with '{report_msg[:min(len(report_msg), 10)]}', full length: {len(report_msg.strip())}", file=sys.stderr)


        return report_msg.strip()

    except Exception as e:
        print(f"DEBUG: Unexpected error in get_market_index for {ticker_symbol}: {e}", file=sys.stderr)
        return f"❌ 讀取 {display_name} 失敗：{e}"


def is_business_day(dt=None):
    import datetime
    import pytz
    import requests

    tz = pytz.timezone("Asia/Taipei")
    if dt is None:
        dt = datetime.datetime.now(tz)
    # 週六週日直接 false
    if dt.weekday() >= 5:
        return False

    # 用公開 API 檢查台灣是否為工作日（政府開放資料）
    today_str = dt.strftime("%Y%m%d")
    try:
        url = f"https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{dt.year}.json"
        res = requests.get(url, timeout=5)
        holiday_list = res.json()
        return holiday_list.get(today_str, 1) == 0
    except:
        # 如果查不到就退而求其次，平日都當作開市
        return True

# ====== 高雄市天氣查詢函數 ======
def get_kaohsiung_weather():
    """
    查詢高雄市今日天氣預報 (來自 CWA F-C0032-001 API)
    包含天氣現象、溫濕度、降雨機率、舒適度，並預測近三日降雨。
    """
    if not CWA_API_KEY:
        return "❌ 氣象查詢失敗：未設定 API 金鑰。"

    LOCATION_NAME = "高雄市"
    # 注意：CWA API 金鑰需要自行申請並正確設定
    CWA_API_URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&locationName={LOCATION_NAME}"

    # emoji 對照表 (天氣的 emoji 似乎沒有問題，保留原樣)
    WEATHER_EMOJI = {
        "晴": "☀️", "多雲": "⛅", "陰": "☁️",
        "雨": "️", "雷": "⛈️", "雪": "❄️", "霧": "️", "陣雨": "️", "雷雨": "⛈️", "多雲時晴": "⛅" # 增加更多天氣描述
    }
    
    def get_emoji(desc):
        # 嘗試精確匹配，如果沒有，再嘗試包含
        for key, emoji in WEATHER_EMOJI.items():
            if desc == key:
                 return emoji
        # 如果沒有精確匹配，嘗試包含關鍵字
        for key, emoji in WEATHER_EMOJI.items():
             if key in desc:
                 return emoji
        # 最後檢查通用雨字
        if "雨" in desc: return "️"
        return "" # 沒有匹配到任何詞

    try:
        print(f"DEBUG: Querying CWA API for {LOCATION_NAME} weather from {CWA_API_URL}.", file=sys.stderr)
        res = requests.get(CWA_API_URL, timeout=10) # 增加超時
        res.raise_for_status()
        data = res.json()

        if data and 'records' in data and 'location' in data['records'] and data['records']['location']:
            location_data = data['records']['location'][0]
            elements = {elem['elementName']: elem for elem in location_data['weatherElement']}
            # Debug: 打印獲取到的所有 weatherElement 名稱
            print(f"DEBUG: CWA API weather elements found for {LOCATION_NAME}: {list(elements.keys())}", file=sys.stderr)


            if 'Wx' in elements and elements['Wx']['time'] and elements['Wx']['time'][0] and 'parameter' in elements['Wx']['time'][0]:
                time0 = elements['Wx']['time'][0]
                wx_desc = time0['parameter'].get('parameterName', '未知天氣')

                min_temp = elements.get('MinT', {}).get('time', [{}])[0].get('parameter', {}).get('parameterName', "N/A")
                max_temp = elements.get('MaxT', {}).get('time', [{}])[0].get('parameter', {}).get('parameterName', "N/A")
                pop_time_list = elements.get('PoP', {}).get('time', [])
                pop = pop_time_list[0].get('parameter', {}).get('parameterName', "N/A") if pop_time_list and pop_time_list[0] and 'parameter' in pop_time_list[0] else "N/A"
                ci_time_list = elements.get('CI', {}).get('time', [])
                comfort = ci_time_list[0].get('parameter', {}).get('parameterName', "N/A") if ci_time_list and ci_time_list[0] and 'parameter' in ci_time_list[0] else "N/A"


                # 判斷未來幾天是否有降雨機率 (F-C0032-001 typically provides 3 periods for PoP)
                rain_in_near_future = False
                if pop_time_list: # 檢查 PoP time list是否存在
                    periods_to_check = min(len(pop_time_list), 3) # 檢查未來3個時段 (通常是未來三天)
                    for i in range(periods_to_check):
                         try:
                             pop_value_str = pop_time_list[i].get('parameter', {}).get('parameterName', '')
                             # 確保 PoP 值是數字且大於 0
                             if pop_value_str and pop_value_str.isdigit():
                                 pop_value = int(pop_value_str)
                                 if pop_value > 0:
                                     rain_in_near_future = True
                                     break # 找到一個就停止檢查
                         except (ValueError, TypeError):
                             # 如果轉換失敗 (例如 " ") 或值無效，跳過此時段
                             continue

                rain_prediction = ""
                if pop_time_list: # 只有在有 PoP 數據時才生成預測文本
                    if rain_in_near_future:
                         rain_prediction = f"預計未來幾天有降雨機率。"
                    else:
                         rain_prediction = f"預計未來幾天無明顯降雨機率。"


                now = datetime.now(tz).strftime("%m/%d %H:%M")
                emoji = get_emoji(wx_desc)
                
                # 天氣預報更新時間格式
                publish_time = data['records']['location'][0]['weatherElement'][0]['time'][0]['startTime']
                publish_time = publish_time[-8:-3]  # "13:00"

                weather_report = (
                    f"{emoji} {LOCATION_NAME} 天氣預報\n"
                    f"天氣：{wx_desc}\n"
                    f"氣溫：{min_temp}°C ～ {max_temp}°C\n"
                    f"降雨機率：{to_emoji_number(pop)}%\n"
                    f"(更新時間：{publish_time})"
                )

                print(f"DEBUG: Final formatted weather report for {LOCATION_NAME}: '{weather_report.strip()[:150]}...'", file=sys.stderr)

                return weather_report.strip()

            else:
                print(f"DEBUG: CWA API response missing required weather elements (Wx, MinT, MaxT, etc.) or time for {LOCATION_NAME}.", file=sys.stderr)
                print(f"DEBUG: CWA API full response (first 500 chars): {str(data)[:500]}...", file=sys.stderr)
                return f"❌ 讀取 {LOCATION_NAME} 天氣失敗：API 響應格式錯誤或無數據。"

        else:
             print(f"DEBUG: CWA API response invalid or empty for {LOCATION_NAME}. No 'records' or 'location'.", file=sys.stderr)
             # 打印完整的 API 響應以幫助除錯
             print(f"DEBUG: CWA API full response (first 500 chars): {str(data)[:500]}...", file=sys.stderr)
             return f"❌ 讀取 {LOCATION_NAME} 天氣失敗：API 響應無效或無資料。"


    except requests.exceptions.RequestException as req_e:
        print(f"DEBUG: Request error querying CWA API from {CWA_API_URL}: {req_e}", file=sys.stderr)
        # 嘗試從響應中獲取狀態碼和文本以提供更詳細的錯誤
        status_code = getattr(req_e.response, 'status_code', 'N/A')
        response_text = getattr(req_e.response, 'text', 'N/A')
        print(f"DEBUG: CWA API Response status: {status_code}, text: {response_text[:150]}...", file=sys.stderr)

        if status_code == 401:
             return f"❌ 氣象查詢失敗：API 金鑰無效或未授權。請檢查 CWA_API_KEY。"
        elif status_code == 403:
             return f"❌ 氣象查詢失敗：API 金鑰權限不足。"
        return f"❌ 氣象查詢失敗：連線錯誤或其他問題 ({status_code}, {req_e})."
    except Exception as e:
        print(f"DEBUG: Unexpected error querying CWA API: {e}", file=sys.stderr)
        return f"❌ 氣象查詢失敗：發生內部錯誤：{e}"


# ====== 高雄市 AQI 空氣品質查詢函數 ======

def get_moea_aqi_value(county="高雄市", site=None):
    url = "https://data.moenv.gov.tw/api/v2/aqx_p_432?api_key=9e565f9a-84dd-4e79-9097-d403cae1ea75&limit=1000&sort=ImportDate desc&format=JSON"
    try:
        res = requests.get(url, timeout=8)
        res.raise_for_status()
        data = res.json()
        sites = [r for r in data["records"] if r["county"] == county]
        if site:
            sites = [r for r in sites if r["sitename"] == site]
        if not sites:
            return None, None, None, None

        rec = sites[0]
        aqi_str = rec.get("aqi", None)
        sitename = rec.get("sitename", "")
        publish_time = (
            rec.get("publishtime")
            or rec.get("PublishTime")
            or rec.get("importdate")
            or rec.get("ImportDate")
            or ""
        )
        try:
            aqi_val = int(aqi_str)
            return aqi_val, "MOENV", sitename, publish_time
        except Exception:
            return None, None, None, None
    except Exception:
        return None, None, None, None

def get_kaohsiung_aqi_aqicn():
    print(f"AQICN token 測試: {AQICN_TOKEN}", file=sys.stderr)
    try:
        url = f"https://api.waqi.info/feed/kaohsiung/?token={AQICN_TOKEN}"
        print(f"查詢網址: {url}", file=sys.stderr)
        r = requests.get(url, timeout=5)
        print(f"API回應: {r.status_code} {r.text[:200]}", file=sys.stderr)
        data = r.json()
        if "data" in data and "aqi" in data["data"]:
            value = data["data"]["aqi"]
            time_str = ""
            if isinstance(data["data"].get("time"), dict):
                time_str = data["data"]["time"].get("s") or data["data"]["time"].get("iso") or ""
            if isinstance(value, int):
                return value, "AQICN", time_str
    except Exception as e:
        print(f"AQICN Exception: {e}", file=sys.stderr)
    return None, None, None

def get_aqi_with_fallback():
    value, src, sitename, time_str = get_moea_aqi_value()
    if value:
        return value, src, sitename, time_str

    value, src, time_str = get_kaohsiung_aqi_aqicn()
    if value:
        return value, f"AQICN國際源", "kaohsiung", time_str

    return None, None, None, None

    # 1. 抓台股大盤K線
import matplotlib
from matplotlib import font_manager as fm
import os

def force_set_chinese_font():
    import matplotlib
    matplotlib.rcParams['font.sans-serif'] = [
        'Noto Sans CJK JP',
        'WenQuanYi Zen Hei',
        'Noto Serif CJK JP',
        'sans-serif'
    ]
    matplotlib.rcParams['axes.unicode_minus'] = False
    print('[DEBUG] 強制中文字型: Noto Sans CJK JP / WenQuanYi Zen Hei / Noto Serif CJK JP / fallback sans-serif')


import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import pytz

def gen_twse_intraday_chart(out_path=None):
    if out_path is None:
        out_path = os.path.join(SHARED_DIR, 'twse_intraday.png')
    tz = pytz.timezone("Asia/Taipei")
    today = datetime.now(tz).strftime('%Y-%m-%d')
    ticker = yf.Ticker("^TWII")
    df = ticker.history(start=today, end=today, interval="5m")
    if df.empty:
        print("抓不到台股分時資料，可能是今天沒開盤")
        return None

    # 畫圖
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(df.index, df['Close'], color='#1f77b4', linewidth=2)
    ax.set_title("台股加權指數(當日走勢)", fontsize=16)
    ax.set_ylabel("指數", fontsize=12)
    ax.set_xlabel("")
    ax.grid(True, linestyle="--", alpha=0.4)

    # X軸只顯示時:分
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()

    # 移除右邊和上方邊框
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches='tight')
    plt.close(fig)
    print(f"[即時走勢] 圖檔已存到 {out_path}")
    return out_path

# 使用自訂prompt
USER_PROMPT_MAP_FILE = "/app/config/user_prompt_map.json"

def get_combined_system_prompt(user_id: str) -> str:
    try:
        # 全域 prompt
        with open('/app/config/global_system_prompt.txt', 'r', encoding='utf-8') as f:
            global_prompt = f.read().strip()

        # 個人差異 prompt
        with open(USER_PROMPT_MAP_FILE, 'r', encoding='utf-8') as f:
            user_prompts = json.load(f)
        personal_prompt = user_prompts.get(user_id, user_prompts.get("Udefault", ""))

        return f"{global_prompt}\n\n{personal_prompt}".strip()
    except Exception as e:
        print(f"ERROR: Failed to combine prompts: {e}", file=sys.stderr)
        return "你是一個擅長分析以及提供資訊的專家。"

# ====== 呼叫 OpenRouter API 的函數 ======
from opencc import OpenCC
t2tw = OpenCC('s2twp')  # 簡體轉台灣正體
# ====== 回應過濾器：移除常見違規格式 ======
def sanitize_llm_reply(reply: str) -> str:
    import re
    # 移除開頭常見的標題段落
    patterns = [
        r"^\*\*回覆內容\s*[:：]\*\*",
        r"^\*\*回答如下\s*[:：]\*\*",
        r"^\*\*以下是.*?\*\*"
    ]
    for pattern in patterns:
        reply = re.sub(pattern, '', reply, flags=re.IGNORECASE).strip()

    # 移除整行為粗體的標題、emoji+粗體、句尾粗體
    lines = reply.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()

        # 1️⃣ **這種**
        if re.fullmatch(r"[\d️⃣⃣🅰-🆎🔟]+\s*\*\*[^*]+\*\*", line):
            continue
        # emoji + **粗體**
        if re.fullmatch(r"[^\w\s]{1,3}\s*\*\*[^*]+\*\*", line):
            continue
        # 整行只有粗體
        if re.fullmatch(r"\*\*[^*]+\*\*", line):
            continue
        # 開頭或結尾是粗體句子也清除粗體符號
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        clean_lines.append(line)

    return '\n'.join(clean_lines).strip()


def get_openrouter_response(prompt: str, config: dict = None) -> str:
    if not client_openrouter:
        print("DEBUG: OpenRouter client not initialized.", file=sys.stderr)
        return "抱歉，聊天服務目前無法使用 (API 設定問題)。"

    try:
        with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
            base_config = json.load(f)
            max_history = int(base_config.get("max_history", 20))

        if config and "user_id" in config:
            system_prompt = get_combined_system_prompt(config["user_id"])
            history_path = get_user_history_file(config["user_id"])
        else:
            system_prompt = "你是一個 LINE 聊天機器人，請使用繁體中文回覆。"
            history_path = HISTORY_FILE

    except Exception as e:
        print(f"ERROR: Failed to load prompt or config: {e}", file=sys.stderr)
        return "❌ 系統提示讀取錯誤。"

    # 準備歷史訊息
    history_messages = []
    try:
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
                valid_pairs = [r for r in records if r.get("user") and r.get("bot")]
                for r in valid_pairs[-max_history:]:
                    history_messages.append({"role": "user", "content": r["user"]})
                    history_messages.append({"role": "assistant", "content": r["bot"]})
    except Exception as e:
        print(f"WARNING: Failed to load history: {e}", file=sys.stderr)

    messages = [{"role": "system", "content": system_prompt}] + \
               history_messages + \
               [{"role": "user", "content": prompt}]

    try:
        completion = client_openrouter.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=messages,
            timeout=30.0
        )
        raw_reply = completion.choices[0].message.content.strip()
        reply = sanitize_llm_reply(t2tw.convert(raw_reply))

        append_history(prompt, reply, user_id=config.get("user_id") if config else None)
        return reply if reply else "⚠️ 沒有收到有效回覆"
    except Exception as e:
        print(f"ERROR: OpenRouter API failed: {e}", file=sys.stderr)
        return "❌ 呼叫 LLM 出錯，請稍後再試。"

# =====統整LLM回答=====
def summarize_with_llm(original_question: str, keyword: str, search_results: list[str], user_id: str = None) -> str:
    if not client_openrouter:
        return "❌ 回覆失敗：LLM 未初始化"

    if not search_results:
        return f"❌ 找不到任何搜尋結果，無法針對「{original_question}」產生回覆。"

    try:
        system_prompt = get_combined_system_prompt(user_id)
        search_block = "\n\n".join(search_results[:5])  # 最多只餵前五筆，避免 token 爆掉
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"""以下是使用者的問題：「{original_question}」
目前系統預測查詢用關鍵字為：「{keyword}」
我們從 Google 搜尋擷取到以下網頁內容（僅供參考，請用你專業整合資訊後回覆）：

{search_block}

請根據以上資訊，用最清楚的方式整理並回答使用者的問題。"""
            }
        ]

        completion = client_openrouter.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=messages,
            timeout=30.0
        )
        raw_reply = completion.choices[0].message.content.strip()
        reply = sanitize_llm_reply(t2tw.convert(raw_reply))

        # 防止空回應
        if not reply or reply.strip() == "":
            return f"❌ 找不到足夠的內容可回應此問題：「{original_question}」。"

        append_history(original_question, reply, user_id=user_id)
        return reply
    except Exception as e:
        print(f"ERROR: summarize_with_llm failed: {e}", file=sys.stderr)
        return "❌ 回覆失敗，可能是 LLM 出錯或搜尋結果過多"

def ask_llm_for_search_keyword(prompt: str) -> str:
    from datetime import datetime

    # 每次呼叫都抓最新時間
    now = datetime.now()
    this_year = now.year
    this_month_chinese = f"{now.month}月"
    correct_date_kw = f"{this_year}年{this_month_chinese}"

    if not client_openrouter:
        return prompt  # LLM壞了就直接回原句查

    try:
        messages = [
            {
                "role": "system",
                "content": "你是一個幫助提取 Google 搜尋關鍵字的工具，不准解釋，只需回傳不超過四組詞組。"
            },
            {
                "role": "user",
                "content": f"""請幫我從以下問題中提取可以拿去 Google 搜尋的查詢用關鍵字，格式如下：

            - 第1組詞組格式為「{correct_date_kw}」，不得修改
            - 第2、3、4組詞組要根據問題內容補主題字詞
            - 最多只准回傳四組詞組，之間用空格分隔，僅限繁體中文
            - 不准回傳句子、不准用引號、不准加註解，只能是一行搜尋用的查詢關鍵字

            問題如下：
            {prompt}
            """
            }
        ]
        completion = client_openrouter.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=messages,
            max_tokens=20,
            temperature=0.2
        )
        result = completion.choices[0].message.content.strip()
        # 強制用寫死的日期，後面接LLM吐的第2、第3、第4組
        kwords = result.replace('\n', ' ').replace('　', ' ').split()
        # 找出所有不是年月的詞組（防LLM又亂回日期）
        non_date_kwords = [w for w in kwords if "年" not in w and "月" not in w]
        # 最多只保留3組非日期主題
        return ' '.join([correct_date_kw] + non_date_kwords[:3])
    except Exception as e:
        print(f"ERROR: ask_llm_for_search_keyword failed: {e}", file=sys.stderr)
        return f"{correct_date_kw} {prompt}"  # fallback



# Webhook 接收路徑
@app.route("/callback", methods=['POST'])

def callback():
    signature = request.headers.get('X-Line-Signature')
    if signature is None:
         print("DEBUG: X-Line-Signature header missing.", file=sys.stderr)
         return 'Missing signature', 400

    body = request.get_data(as_text=True)

    print(f"DEBUG: Received X-Line-Signature: '{signature}'", file=sys.stderr)
    print(f"DEBUG: Received Request body: '{body}'", file=sys.stderr)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Please check your channel access token/channel secret.")
        print("DEBUG: InvalidSignatureError caught. Returning 400.", file=sys.stderr)
        return 'Invalid signature', 400
    except Exception as e:
        app.logger.error(f"Error processing webhook: {e}")
        print(f"DEBUG: Other exception caught: {e}. Returning 500.", file=sys.stderr)
        # 返回一個通用錯誤信息，避免洩露內部細節
        return 'Internal server error', 500

    print("DEBUG: Webhook handler finished successfully. Returning 200 OK.", file=sys.stderr)
    return 'OK', 200

# ====== 應用程式啟動時執行 (模組載入階段) ======
# 這些程式碼會在 Gunicorn 載入 worker 模組時執行
print("DEBUG: Executing module-level code to load prompt and start scheduler...", file=sys.stderr) # 新增 debug 打印

# 應用程式啟動時，先載入一次 Prompt
load_llm_prompt()

# 設定定時任務，每隔指定分鐘執行一次載入函式
if LLM_PROMPT_FILE: # 只有在設定了檔案路徑時才啟動定時任務
    print(f"DEBUG: Scheduling prompt reload every {LLM_POLLING_INTERVAL_MINUTES} minutes.", file=sys.stderr) # 新增 debug 打印
    schedule.every(LLM_POLLING_INTERVAL_MINUTES).minutes.do(load_llm_prompt)

    # 啟動背景執行緒來運行排程器
    # 設置為 daemon=True 確保主程式結束時執行緒也會自動結束
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("INFO: LLM prompt file auto-reload scheduler thread started.", file=sys.stderr)
else:
    print("INFO: LLM_PROMPT_FILE not set, auto-reload scheduler will not start.", file=sys.stderr)

print("DEBUG: Finished module-level code.", file=sys.stderr) # 新增 debug 打印

# ====== LINE 事件處理器 ======
# 保持原樣
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text_from_user = event.message.text.strip()
    reply_token = event.reply_token
    source_user_id = event.source.user_id

    print(f"DEBUG: Received MessageEvent from {source_user_id}. Text: '{text_from_user}'", file=sys.stderr)

    # 初始化 reply_text 為 None，表示預設不回覆
    reply_text = None

    # ====== 處理特定指令 (「盤子」查詢) ======
    if text_from_user == "盤子":
        market_report = get_market_index()
        tsmc_report = get_stock_price("2330", "台積電")
        weather_raw = get_kaohsiung_weather()
        weather_line = weather_raw.strip()
        aqi_value, aqi_source, aqi_sitename, _ = get_aqi_with_fallback()
        aqi_emoji = get_aqi_emoji(aqi_value) if aqi_value else "❓"
        aqi_comment = get_aqi_comment(aqi_value)
        aqi_line = f"🍃 AQI：{aqi_emoji} {to_emoji_number(aqi_value) if aqi_value else '❓'}（{aqi_sitename if aqi_sitename else ''}）\n{aqi_comment}"

        market_lines = market_report.split('\n')
        tsmc_lines = tsmc_report.split('\n')
        market_simple = '\n'.join(market_lines[:3])
        tsmc_simple = '\n'.join(tsmc_lines[:3])

        combined_report = (
            f"{market_simple}\n\n"
            f"{tsmc_simple}"
        )

        weather_img_url, twse_img_url = None, None
        messages = [TextMessage(text=combined_report)]

        # 產圖流程直接在主 thread 等待
        if is_business_day():
            try:
                weather_data = get_kaohsiung_weather_dict()
                aqi_data = get_kaohsiung_aqi_dict()
                html = build_weather_aqi_html(weather_data, aqi_data)
                weather_img_url = render_html_to_image(html)
            except Exception as e:
                print(f"產天氣圖卡掛掉：{e}", file=sys.stderr)
            try:
                subprocess.run(
                    ["/usr/local/bin/python3", "/app/plot_twse_intraday.py"],
                    check=True,
                )
                twse_img_url = f"https://rpi.kuies.tw/static/twse_intraday.png?nocache={random.randint(1000,9999)}"
            except Exception as e:
                print(f"產分時圖掛掉：{e}", file=sys.stderr)

            # 只要圖有成功，直接組進 reply_message
            if weather_img_url:
                messages.append(ImageMessage(
                    original_content_url=weather_img_url,
                    preview_image_url=weather_img_url
                ))
            if twse_img_url:
                messages.append(ImageMessage(
                    original_content_url=twse_img_url,
                    preview_image_url=twse_img_url
                ))

        # 不用 threading，不用 push_message，直接 reply_message
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages
                )
            )
        return "OK"

        # 先產圖
        img_path = gen_twse_intraday_chart()
        img_url = "https://rpi.kuies.tw/static/twse_intraday.png"

        messages = [TextMessage(text=combined_report)]
        if weather_img_url:
            messages.append(ImageMessage(
                original_content_url=weather_img_url,
                preview_image_url=weather_img_url
            ))
        if twse_img_url:
            messages.append(ImageMessage(
                original_content_url=twse_img_url,
                preview_image_url=twse_img_url
            ))

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages
                )
            )
        return "OK"

    # ====== 新增新聞爬蟲功能 ======
    elif text_from_user == "新聞":
        print(f"DEBUG: Matched '新聞' command. Fetching news...", file=sys.stderr)
        news_result = ""  # ✅ 預設初始化
        try:
            ltn_news = get_ltn_politics_news()
            news_result = "自由時報政治新聞（最新三則）：\n"  # ✅ 重新賦值
            for news in ltn_news:
                news_result += f"{news['title']}\n{news.get('summary', '')}...\n{news['url']}\n\n"
        except Exception as e:
            print(f"ERROR: Failed to fetch news: {e}", file=sys.stderr)
            news_result = "新聞資訊暫時無法取得，請稍後再試。"  # ✅ 預設錯誤訊息
        reply_text = news_result.strip()

     # ====== LLM 聊天整合：檢查是否以「哥哥找 哥哥查」開頭 ======
    elif text_from_user.startswith("哥哥查") or text_from_user.startswith("哥哥找"):
        original_question = text_from_user.replace("哥哥查", "").replace("哥哥找", "").strip()
        print(f"DEBUG: Matched '哥哥查/找' trigger. Extracted question: '{original_question}'", file=sys.stderr)

        keyword = ask_llm_for_search_keyword(original_question)
        print(f"DEBUG: Predicted search keyword: '{keyword}'", file=sys.stderr)

        try:
            search_results = search_google_with_content(keyword, max_links=10, target_success=3)
        except Exception as e:
            print(f"ERROR: Playwright search failed: {e}", file=sys.stderr)
            reply_text = "❌ 搜尋時出錯，請稍後再試。"
            search_results = []

        valid_results = [r for r in search_results if not r.startswith("❌")]

    # ⚠️ 若資料過少，自動簡化關鍵詞後重查
        if len(valid_results) < 3 and len(keyword.split()) > 2:
            simplified_keyword = " ".join(keyword.split()[:2])
            print(f"⚠️ 自動簡化搜尋關鍵詞後重查：{simplified_keyword}", file=sys.stderr)
            try:
                search_results = search_google_with_content(simplified_keyword, max_links=10, target_success=3)
            except Exception as e:
                print(f"ERROR: Fallback Playwright search failed: {e}", file=sys.stderr)
                search_results = []
            valid_results = [r for r in search_results if not r.startswith("❌")]

        if len(valid_results) < 3:
            print(f"DEBUG: Results too few ({len(valid_results)}), fetching Google News RSS...", file=sys.stderr)
            news_results = fetch_google_news_rss(keyword, max_items=3 - len(valid_results))
            valid_results.extend(news_results)

    # ✅ 回覆邏輯
        if len(valid_results) < 2:
            reply_text = f"❌ 找不到足夠的資訊來回覆：「{original_question}」。可能搜尋結果太少或資料不足。\n\n以下是擷取摘要（{len(valid_results)} 筆）：\n"
            for i, snippet in enumerate(valid_results):
                first_line = snippet.split("\n")[0][:50]
                reply_text += f"{i+1}. {first_line}\n"
            print(f"DEBUG: valid_results count = {len(valid_results)}", file=sys.stderr)
        else:
            reply_text = summarize_with_llm(original_question, keyword, valid_results, source_user_id)

    # ====== LLM 聊天整合：檢查是否以「哥哥」開頭 ======
    # 使用 elif 確保只有沒有匹配到「盤子」時才進入 LLM 判斷
    elif text_from_user.startswith("哥哥"):
        llm_prompt = text_from_user[len("哥哥"):].strip()
        print(f"DEBUG: Matched '哥哥' trigger. Extracted prompt: '{llm_prompt[:100]}...'", file=sys.stderr)

        if client_openrouter:
           # ✅ 加入 user_id 給 get_openrouter_response() 用
            config = {
                "system_prompt": "placeholder",  # 原來的沒用，會被 get_user_prompt 覆蓋
                "user_id": source_user_id
            }
            reply_text = get_openrouter_response(llm_prompt, config)
        else:
            reply_text = "抱歉，聊天服務目前無法使用 (API 設定問題)。"


    # ====== 預設行為：不回覆 ======
    # 如果沒有匹配到任何指令或 LLM 觸發關鍵字，reply_text 保持為 None
    else:
        print(f"DEBUG: No specific command ('盤子') or LLM trigger ('哥哥') matched. No automatic reply sent for text: '{text_from_user}'.", file=sys.stderr)
        # reply_text 保持為 None


    # ====== 回覆訊息給使用者 (只有 reply_text 不是 None 時才回覆) ======
    # 檢查 LINE_CHANNEL_ACCESS_TOKEN 是否存在，這是發送訊息必需的
    if reply_text and reply_text.strip(): # 檢查是否需要回覆
        if LINE_CHANNEL_ACCESS_TOKEN:
            try:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=reply_text)]
                        )
                    )
                    print(f"DEBUG: Replied successfully to {reply_token} from {source_user_id}.", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
            except Exception as e:
                 print(f"DEBUG: Error sending reply message: {e}", file=sys.stderr)
                 print(f"DEBUG: Reply failed for token: {reply_token}, from user: {source_user_id}. Message content (first 150 chars): '{reply_text[:150]}...'", file=sys.stderr)
                 # 選擇性：可以在這裡向用戶發送一個錯誤回覆，說明發送失敗
                 # try:
                 #     with ApiClient(configuration) as api_client:
                 #         line_bot_api = MessagingApi(api_client)
                 #         line_bot_api.push_message(source_user_id, TextMessage(text=f"回覆失敗：{e}"))
                 # except Exception as push_e:
                 #     print(f"DEBUG: Failed to send error push message: {push_e}", file=sys.stderr)

        else:
            print(f"WARNING: LINE_CHANNEL_ACCESS_TOKEN not set. Cannot send reply message.", file=sys.stderr)
            print(f"WARNING: Attempted to reply with: '{reply_text[:50]}...' but token is missing.", file=sys.stderr)
    else:
        # 如果 reply_text is None，表示不需要回覆，這裡不執行任何動作
        pass # 已在 else 塊打印 Debug 信息

    # ===== 整合 search_google 進 line_webhook_app =====
from bs4 import BeautifulSoup
from readability import Document
from playwright.sync_api import sync_playwright
import requests, os

def fetch_firecrawl_content(url: str) -> str:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    res = requests.post("https://api.firecrawl.dev/v0/scrape", json={"url": url}, headers=headers, timeout=15)
    return res.json().get("text", "")

def search_google_with_content(query: str, max_links: int = 30, target_success: int = 3) -> list[str]:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)...")
        page = context.new_page()
        page.goto(f"https://www.google.com/search?q={query}", timeout=60000)
        page.wait_for_timeout(2000)

        # ✅ 新版：從 a[href^="/url?q="] 中解析出真實連結
        link_elements = page.query_selector_all("a")
        raw_links = []
        for a in link_elements:
            href = a.get_attribute("href")
            if href and href.startswith("/url?q="):
                real_url = href.split("/url?q=")[1].split("&")[0]
                if (
                    real_url.startswith("http") and
                    "google.com" not in real_url and
                    "facebook.com" not in real_url and
                    "youtube.com" not in real_url and
                    "pinterest.com" not in real_url
                ):
                    raw_links.append(real_url)
            if len(raw_links) >= max_links:
                break

        print(f"DEBUG: 取得有效搜尋連結 {len(raw_links)} 筆", file=sys.stderr)

        # ✅ 成功擷取至少 target_success 筆內文才回傳
        for url in raw_links:
            try:
                new_page = context.new_page()
                new_page.goto(url, timeout=20000, wait_until="domcontentloaded")
                new_page.wait_for_timeout(1000)
                html = new_page.content()
                doc = Document(html)
                readable_html = doc.summary()
                soup = BeautifulSoup(readable_html, "html.parser")
                summary = soup.get_text(strip=True)[:800]
                new_page.close()

                # Firecrawl fallback
                if len(summary.strip()) < 80:
                    print(f"⚠️ Playwright 內容過短（{len(summary)}），Firecrawl 擷取：{url}", file=sys.stderr)
                    summary = fetch_firecrawl_content(url)[:800]

                if len(summary.strip()) >= 80:
                    print(f"✅ 成功擷取 from {url}，長度：{len(summary)} 字", file=sys.stderr)
                    results.append(f"🔗 來源：{url}\n📄 內文擷取：\n{summary}")
                else:
                    print(f"⚠️ 內容過短（{len(summary)} 字），略過：{url}", file=sys.stderr)

            except Exception as e:
                print(f"❌ 擷取失敗：{e} for {url}", file=sys.stderr)

            if len(results) >= target_success:
                break

        browser.close()
    return results

def fetch_google_news_rss(query: str, max_items: int = 3) -> list[str]:
    """Fetch Google News RSS articles for the query and return summaries."""
    rss_url = (
        "https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    results = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:max_items]:
            url = entry.link
            summary = fetch_firecrawl_content(url)[:800]
            if len(summary.strip()) < 80 and hasattr(entry, "summary"):
                summary = BeautifulSoup(entry.summary, "html.parser").get_text(strip=True)[:800]
            if summary:
                results.append(f"🔗 來源：{url}\n📄 內文擷取：\n{summary}")
    except Exception as e:
        print(f"WARNING: Google News RSS fetch failed: {e}", file=sys.stderr)
    return results
    
# =====天氣轉HTML模板=====
def get_weather_bg(desc):
    desc = desc or ""
    if "晴" in desc:
        return "linear-gradient(120deg,#fffbe9,#ffe089 70%,#ffd566)"
    elif "雨" in desc:
        return "linear-gradient(120deg,#e3f3fe 40%,#b3cdfc 70%,#8da7e8)"
    elif "雪" in desc or "寒" in desc or "冷" in desc:
        return "linear-gradient(120deg,#f0f4fa 40%,#c3d3e6 70%,#b4c7d6)"
    elif "陰" in desc or "雲" in desc:
        return "linear-gradient(120deg,#ececec 40%,#c8d6e2 70%,#cfcfd7)"
    else:
        return "linear-gradient(120deg,#fff9f9,#f0faff)"

def get_weather_icon(desc: str) -> str:
    """Return an emoji icon matching the weather description."""
    desc = desc or ""
    if "晴" in desc:
        return "☀️"
    elif "雨" in desc:
        return "🌧"
    elif "雪" in desc or "寒" in desc or "冷" in desc:
        return "❄️"
    elif "陰" in desc or "雲" in desc:
        return "☁️"
    else:
        return "🌤"


def build_weather_aqi_html(weather: dict, aqi: dict) -> str:
    """Generate an HTML snippet for the weather/AQI card."""
    bg = get_weather_bg(weather.get("desc"))
    icon = get_weather_icon(weather.get("desc"))
    return f"""
    <html>
    <body style="margin:0;padding:0;">
    <div id="screenshot-target" style="width:360px;height:300px;position:relative;
        background:{bg};
        padding:22px 28px;box-sizing:border-box;
        font-family:'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;
        color:#333;border-radius:40px;box-shadow:0 2px 18px #eee;">

      <div style="position:absolute;right:26px;bottom:20px;font-size:88px;opacity:0.15;pointer-events:none;">
        {icon}
      </div>

      <div style="font-size:22px;font-weight:bold;margin-bottom:14px;">
        🌤 {weather.get("location","地區")} 天氣與空氣品質
      </div>

      <div style="font-size:15.5px;line-height:1.7;">
        ☀️ 天氣：{weather.get("desc","N/A")}<br>
        🌡 溫度：{weather.get("min_temp","-")}°C ~ {weather.get("max_temp","-")}°C<br>
        🌧 降雨率：{weather.get("pop","-")}%<br><br>

        🍃 測站：{aqi.get("station","N/A")}<br>
        📏 AQI：{aqi.get("value","N/A")}<br>
        ⚠️ 狀態：{aqi.get("status","N/A")}<br>
        <span style="font-size:12px;color:#888;">🗓 資料時間：{aqi.get("time","N/A")}</span>
      </div>
    </div>
    </body>
    </html>
    """
    return html

import uuid

def render_html_to_image(html_content: str) -> str:
    try:
        print("🧪 render_html_to_image(): 發送 HTML 給 html2img container...", file=sys.stderr)
        response = requests.post(
            "http://html2img:3000/render",
            data=html_content.encode("utf-8"),
            headers={"Content-Type": "text/html"},
            timeout=15,
        )
        if response.status_code == 200:
            info = response.json()
            filename = info.get("filename")
            if not filename:
                raise ValueError("Missing filename in html2img response")

            src_path = os.path.join(SHARED_DIR, filename)
            dst_filename = f"{uuid.uuid4().hex}.png"
            dst_path = os.path.join(SHARED_DIR, dst_filename)
            shutil.copy(src_path, dst_path)
            print(f"✅ 圖片成功儲存：{dst_path}", file=sys.stderr)
            # **這裡改成 /static 路徑**
            return f"https://rpi.kuies.tw/static/{dst_filename}"
        else:
            print(
                f"❌ HTML2IMG 失敗：{response.status_code}, {response.text}",
                file=sys.stderr,
            )
            return "https://i.imgur.com/yT8VKpP.png"
    except Exception as e:
        print(f"❌ HTML2IMG 呼叫錯誤：{e}", file=sys.stderr)
        return "https://i.imgur.com/yT8VKpP.png"


def get_kaohsiung_weather_dict() -> dict:
    """Return weather information for Kaohsiung as a dictionary."""
    if not CWA_API_KEY:
        raise ValueError("CWA_API_KEY not set")

    url = (
        "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
        f"?Authorization={CWA_API_KEY}&locationName=高雄市"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()

    loc = data.get("records", {}).get("location", [{}])[0]
    elements = {e["elementName"]: e for e in loc.get("weatherElement", [])}

    def elem_val(name: str) -> str:
        return (
            elements.get(name, {})
            .get("time", [{}])[0]
            .get("parameter", {})
            .get("parameterName", "N/A")
        )

    return {
        "location": "高雄市",
        "desc": elem_val("Wx"),
        "min_temp": elem_val("MinT"),
        "max_temp": elem_val("MaxT"),
        "pop": elem_val("PoP"),
        "comfort": elem_val("CI"),
    }


def get_kaohsiung_aqi_dict() -> dict:
    value, _, sitename, time_str = get_aqi_with_fallback()
    return {
        "station": sitename or "",
        "value": value if value is not None else "N/A",
        "status": get_aqi_comment(value),
        "time": time_str or datetime.now(tz).strftime("%H:%M"),
    }



def send_extra_images(user_id: str, weather_img_url: Optional[str], twse_img_url: Optional[str]) -> None:
    """Push extra images to LINE user if available."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("WARNING: LINE_CHANNEL_ACCESS_TOKEN not set. Cannot send extra images.", file=sys.stderr)
        return

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            messages = []
            if weather_img_url:
                messages.append(
                    ImageMessage(
                        original_content_url=weather_img_url,
                        preview_image_url=weather_img_url,
                    )
                )
            if twse_img_url:
                messages.append(
                    ImageMessage(
                        original_content_url=twse_img_url,
                        preview_image_url=twse_img_url,
                    )
                )
            if messages:
                req = PushMessageRequest(to=user_id, messages=messages)
                line_bot_api.push_message_with_http_info(
                    req,
                    x_line_retry_key=str(uuid.uuid4())
                )
    except Exception as e:
        print(f"DEBUG: Failed to push extra images: {e}", file=sys.stderr)


# 新增環境變數：對話歷史檔路徑，可在 .env 裡設定
def get_user_history_file(user_id: str) -> str:
    folder = "history"  # 相對於 config 同層的 history 資料夾
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"history_{user_id}.json")

# 對應 ID → 使用者名稱
USER_NAME_MAP = {
    "Ue61d9b3a2353792e6921607c2f671c96": "凱翔",
    "U0476131f6dec9a63c665a4e7795909db": "阿修",
    "Ua1c92f5b5e5ea26ba59b2ced88d880f7": "吳小心",
    "U77978db6c0da105a7cadcb5b49a0177b": "廣廣"
}
# 歷史檔案改為依 user_id 存放
def get_user_history_file(user_id: str) -> str:
    return f"/app/config/history_{user_id}.json"

def append_history(user_prompt, bot_reply, user_id=None):
    """把對話紀錄寫入使用者歷史檔，並標註說話者名稱"""
    try:
        history_data = []
        history_path = get_user_history_file(user_id)

        # ✅ 正確讀舊資料
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                try:
                    history_data = json.load(f)
                    if not isinstance(history_data, list):
                        print(f"WARNING: {history_path} is not a list. Resetting.", file=sys.stderr)
                        history_data = []
                except json.JSONDecodeError as e:
                    print(f"ERROR: JSON decode error in {history_path}: {e}.", file=sys.stderr)
                    history_data = []

        # ✅ 加入新的對話紀錄
        today = datetime.today().strftime('%Y-%m-%d')
        username = USER_NAME_MAP.get(user_id, f"ID:{user_id}" if user_id else "未知使用者")

        record = {
            'date': today,
            'user': f"{username}：{user_prompt}",
            'bot': bot_reply
        }
        history_data.append(record)

        # 限制最多保留50筆
        if len(history_data) > 50:
            history_data = history_data[-50:]

        # ✅ 正確寫入更新後內容
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        print(f"DEBUG: Appended conversation to {history_path}.", file=sys.stderr)

    except Exception as e:
        print(f"ERROR: append_history failed: {e}", file=sys.stderr)

# 對話備份排程
def backup_all_user_histories():
    for filename in os.listdir('/app/config'):
        if filename.startswith('history_U') and filename.endswith('.json'):
            uid = filename.split('_')[1].split('.')[0]
            today = datetime.today().strftime('%Y%m%d')
            src = f"/app/config/{filename}"
            dst = f"/app/config/{filename.replace('.json', f'_{today}.json')}"
            shutil.copy(src, dst)
            with open(src, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

# 加入定時任務：
schedule.every().day.at("00:00").do(backup_all_user_histories)