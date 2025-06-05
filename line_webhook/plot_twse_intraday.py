import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import numpy as np
import matplotlib.ticker as mticker
import datetime
import os

from matplotlib.font_manager import FontProperties

import numpy as np
from scipy.interpolate import make_interp_spline

SHARED_DIR = os.getenv("SHARED_DIR", "/shared")
OUT_PATH = os.path.join(SHARED_DIR, "twse_intraday.png")

today_str = datetime.datetime.now().strftime("%Y-%m-%d")
csv_path = os.path.join(SHARED_DIR, f"twse_intraday_{today_str}.csv")

if not os.path.exists(csv_path):
    candidates = [
        f
        for f in os.listdir(SHARED_DIR)
        if f.startswith("twse_intraday_") and f.endswith(".csv")
    ]
    if not candidates:
        raise FileNotFoundError("沒有任何分時資料檔案")
    latest = max(candidates, key=lambda f: os.path.getmtime(os.path.join(SHARED_DIR, f)))
    csv_path = os.path.join(SHARED_DIR, latest)

df = pd.read_csv(csv_path)

file_date = pd.to_datetime(df["datetime"].iloc[0]).strftime("%Y-%m-%d")

# 轉成datetime格式
df["datetime"] = pd.to_datetime(df["datetime"])

# ==== 重點：建立完整X軸（09:00~13:30，每分鐘一格）====
start_time = pd.to_datetime(f"{file_date} 09:00")
end_time = pd.to_datetime(f"{file_date} 13:30")
full_time_index = pd.date_range(start=start_time, end=end_time, freq="1T")
df = df.set_index("datetime")
df = df[~df.index.duplicated(keep='first')]
df = df.reindex(full_time_index)
# 只前向補到最後一筆有成交，其餘留白
last_valid = df["price"].last_valid_index()
df.loc[:last_valid, "price"] = df.loc[:last_valid, "price"].ffill()
df.loc[last_valid:, "price"] = np.nan
df.index.name = "datetime"

# ==== 重點結束 ====

# 字型路徑
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
myfont = fm.FontProperties(fname=FONT_PATH)

fig, ax = plt.subplots(figsize=(10, 5))

# 畫基準線（開盤0%線）
base = df["price"].dropna().iloc[0]
ax.axhline(y=base, color="black", linestyle="--", linewidth=1)

# 斷色平滑分段+填色（超像APP）
price = df["price"].values
x = np.arange(len(price))
base = df["price"].dropna().iloc[0]

# 找出所有不是NaN的index
valid_idx = np.where(~np.isnan(price))[0]

# 1. 找交點(基準線交會的時間戳)
def interp_time(t1, t2, y1, y2, base):
    # t1, t2 都是 Timestamp
    ratio = (base - y1) / (y2 - y1)
    return t1 + (t2 - t1) * ratio

# 分段：遇到穿越基準線的位置就斷
segments = []
cur_idx = valid_idx[0]
while cur_idx < valid_idx[-1]:
    for nxt in range(cur_idx+1, valid_idx[-1]+1):
        if np.isnan(price[nxt]):
            break
        y1, y2 = price[cur_idx], price[nxt]
        if (y1 - base) * (y2 - base) < 0:
            # 交點
            t1, t2 = df.index[cur_idx], df.index[nxt]
            cross_time = interp_time(t1, t2, y1, y2, base)
            # 本段：cur_idx ~ cross_time（只包含交點一次，不重疊給下一段）
            seg_time = df.index[cur_idx:nxt].append(pd.DatetimeIndex([cross_time]))
            seg_y = np.append(price[cur_idx:nxt], base)
            segments.append((seg_time, seg_y))
            cur_idx = nxt  # 下一段直接從nxt開始（不再append cross_time給下一段）
            break
    else:
        seg_time = df.index[cur_idx:valid_idx[-1]+1]
        seg_y = price[cur_idx:valid_idx[-1]+1]
        segments.append((seg_time, seg_y))
        break

# 畫每一段（平滑+正確填色）
from itertools import groupby

for seg_time, seg_y in segments:
    # 平滑插值
    if len(seg_time) > 2:
        # 不要用100點！直接用原始點數
        ts = np.arange(len(seg_time))
        # 強制平滑點數維持原始，每個segment都對齊交會點
        spline = make_interp_spline(ts, seg_y, k=2)
        ts_dense = np.linspace(0, len(seg_time)-1, 10*len(seg_time))  # 細緻插值但頭尾一定在
        line_y = spline(ts_dense)
        # 時間也要同步插補
        time_interp = np.linspace(seg_time[0].value, seg_time[-1].value, 10*len(seg_time))
        line_time = pd.to_datetime(time_interp)
    else:
        line_y = seg_y
        line_time = seg_time

    # 這邊才是正解分段！(分成連續紅綠片段)
    above = line_y >= base
    last = 0
    for key, group in groupby(enumerate(above), key=lambda x: x[1]):
        idx_group = [i for i, is_above in group]
        if not idx_group:
            continue
        color = "red" if key else "green"
        # 注意：分段要連續，不然會出現斷層
        ax.plot(line_time[idx_group], line_y[idx_group], color=color, linewidth=2)
        ax.fill_between(line_time[idx_group], base, line_y[idx_group], color=color, alpha=0.18)

# 指定你要的時間tick
xlabels = [
    pd.to_datetime(f"{file_date} 09:00"),
    pd.to_datetime(f"{file_date} 10:00"),
    pd.to_datetime(f"{file_date} 11:00"),
    pd.to_datetime(f"{file_date} 12:00"),
    pd.to_datetime(f"{file_date} 13:00"),
    pd.to_datetime(f"{file_date} 13:30")
]
ax.set_xticks(xlabels)
ax.set_xticklabels([dt.strftime("%H:%M") for dt in xlabels], fontproperties=myfont)

# X軸label美化（不用再用fig.autofmt_xdate）
plt.setp(ax.get_xticklabels(), rotation=0, ha="center")

# 雙Y軸右側
if df["price"].notna().any():
    base = df["price"].dropna().iloc[0]
    df["pct"] = (df["price"] - base) / base * 100
    ax2 = ax.twinx()
    ax2.set_ylabel("漲跌幅(%)", fontsize=12, fontproperties=myfont)
    ax2.set_ylim((df["pct"].min(), df["pct"].max()))
    ax2.yaxis.grid(False)
    yticks = np.linspace(df["pct"].min(), df["pct"].max(), 5)
    ax2.set_yticks(yticks)
    labels = []
    for v in yticks:
        if v > 0:
            labels.append(f"+{v:.2f}%")
        else:
            labels.append(f"{v:.2f}%")
    ax2.set_yticklabels(labels)
    for label in ax2.get_yticklabels():
        try:
            v = float(label.get_text().replace('%','').replace('+',''))
            if v > 0:
                label.set_color('red')
            else:
                label.set_color('green')
        except Exception:
            label.set_color('black')

plt.tight_layout()
plt.savefig(OUT_PATH, bbox_inches='tight')
plt.close(fig)
print("圖已輸出:", OUT_PATH)
