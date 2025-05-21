import requests
import csv
from datetime import datetime
import os
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Noto Sans CJK TC']
matplotlib.rcParams['axes.unicode_minus'] = False  # 保證負號正常顯示

CSV_PATH = "/home/kuies/html2img_output/twse_intraday.csv"

def get_twse_tick():
    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0"
    try:
        info = requests.get(url, timeout=5).json()['msgArray'][0]
        now = info['z']
        t = info['t']  # 格式 13:28:30
        dt = datetime.now().strftime("%Y-%m-%d") + " " + t  # 2025-05-20 13:28:30
        return [dt, now]
    except Exception as e:
        print("API ERROR:", e)
        return None

def append_tick():
    tick = get_twse_tick()
    if not tick or tick[1] in ('', '-', '---'):
        print("沒抓到數據，跳過")
        return
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["datetime", "price"])
        writer.writerow(tick)
    print("已存:", tick)

if __name__ == "__main__":
    append_tick()