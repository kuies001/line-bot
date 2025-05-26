import requests
import csv
import os
import time
import sys
from datetime import datetime

CSV_PATH = "twse_intraday.csv"  # 修正為當前目錄

def get_twse_tick():
    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0"
    try:
        info = requests.get(url, timeout=5).json()['msgArray'][0]
        now = info['z']
        t = info['t']  # 格式 09:00:00
        dt = datetime.now().strftime("%Y-%m-%d") + " " + t
        return [dt, now]
    except Exception as e:
        print("API ERROR:", e)
        return None

def last_record_datetime():
    try:
        with open(CSV_PATH, "r") as f:
            lines = f.readlines()
            if lines:
                return lines[-1].split(",")[0].strip()
    except:
        pass
    return None

def append_tick(tick):
    if not tick or tick[1] in ('', '-', '---'):
        print("沒抓到數據，跳過")
        return
    last_dt = last_record_datetime()
    if last_dt == tick[0]:
        print("重複時間，不寫入")
        return
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["datetime", "price"])
        writer.writerow(tick)
    print("已存:", tick)

if __name__ == "__main__":
    print("爆打流全自動開始！")
    while True:
        now = datetime.now()
        # 只管交易日，其他直接停掉（可加判斷禮拜幾，不想就讓他無限睡）
        h, m = now.hour, now.minute

        # 測試模式強制運行
        if '--test' in sys.argv:  # 統一使用 --test 參數檢查
            pass  # 跳過時間檢查
        # 原收盤時間檢查
        elif h > 13 or (h == 13 and m >= 32):
            print("收盤，程式結束，明天見！")
            break

        # 08:59~09:01 爆打，2秒一抓
        if h == 8 and m == 59:
            end_time = now.replace(hour=9, minute=1, second=0, microsecond=0)
            while datetime.now() < end_time:
                tick = get_twse_tick()
                append_tick(tick)
                time.sleep(2)
            print("爆打收盤，進入盤中模式")
            continue  # 防止剛好卡在09:01又多打一筆

        # 09:01~13:31 盤中 10秒一抓
        if (h == 9 and m >= 1) or (h in [10, 11, 12]) or (h == 13 and m <= 31):
            tick = get_twse_tick()
            append_tick(tick)
            time.sleep(10)
            continue

        # 測試模式強制生成數據
        if '--test' in sys.argv:
            test_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            test_price = str(round(17000 + (datetime.now().minute * 10), 2))
            append_tick([test_time, test_price])
            time.sleep(3)  # 每3秒生成一筆測試數據
        else:
            # 其他時段直接睡到08:59
            sleep_sec = 60
            print("現在不是交易時段，睡一下")
            time.sleep(sleep_sec)
