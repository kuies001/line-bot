import requests
import csv
import os
import time
import sys
import gzip
import shutil
from datetime import datetime, timedelta

SHARED_DIR = os.getenv("SHARED_DIR", "/shared")
ARCHIVE_DIR = os.path.join(SHARED_DIR, "archive")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

TODAY_STR = datetime.now().strftime("%Y-%m-%d")
CSV_PATH = os.path.join(SHARED_DIR, f"twse_intraday_{TODAY_STR}.csv")

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
    # 获取CSV最后一行的完整时间戳
    last_dt = last_record_datetime()
    
    # 当CSV不为空时，严格比较完整时间戳
    if last_dt and last_dt == tick[0]:
        print(f"數據未更新 ({tick[0]})，跳過寫入")
        return
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["datetime", "price"])
        writer.writerow(tick)
    print("已存:", tick)


def archive_old_csv(days: int = 7):
    """Compress CSV files older than the given days into the archive directory."""
    now = datetime.now()
    for fname in os.listdir(SHARED_DIR):
        if not fname.startswith("twse_intraday_") or not fname.endswith(".csv"):
            continue
        fpath = os.path.join(SHARED_DIR, fname)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
        if now - mtime > timedelta(days=days):
            gz_name = fname + ".gz"
            gz_path = os.path.join(ARCHIVE_DIR, gz_name)
            with open(fpath, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(fpath)
            print(f"Archived {fname} -> {gz_path}")

if __name__ == "__main__":
    print("爆打流全自動開始！")

    end_time = datetime.now().replace(hour=13, minute=30, second=0, microsecond=0)

    if '--test' not in sys.argv and datetime.now() > end_time:
        print("已過收盤時間，程式結束")
        sys.exit(0)

    while True:
        now = datetime.now()
        if '--test' in sys.argv:
            tick = [now.strftime("%Y-%m-%d %H:%M:%S"), str(round(17000 + now.minute * 10, 2))]
        else:
            if now > end_time:
                break
            tick = get_twse_tick()

        append_tick(tick)
        time.sleep(2)

    print("收盤，程式結束")
    archive_old_csv()
