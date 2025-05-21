import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import numpy as np
import matplotlib.ticker as mticker

from matplotlib.font_manager import FontProperties

CSV_PATH = "/shared/twse_intraday.csv"
OUT_PATH = "/shared/twse_intraday.png"

df = pd.read_csv(CSV_PATH)
df["datetime"] = pd.to_datetime(df["datetime"])

# 明確指定你剛查到的ttc路徑
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
myfont = fm.FontProperties(fname=FONT_PATH)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(df["datetime"], df["price"], color="#2299FF", linewidth=2)
ax.fill_between(df["datetime"], df["price"], df["price"].min(), color="#66CCFF", alpha=0.3)

import matplotlib.dates as mdates

# 設定 x 軸主刻度顯示格式，直接 yyyy-mm-dd HH:MM
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 30)))
fig.autofmt_xdate(rotation=30)

# 讓label斜一點比較好看
fig.autofmt_xdate(rotation=30)

date_str = df["datetime"].dt.strftime("%-m/%-d").iloc[0]  # 會顯示 5/21
ax.set_title(f"台股加權指數({date_str} 當日走勢)", fontsize=16, fontproperties=myfont)
ax.set_ylabel("指數", fontsize=12, fontproperties=myfont)
ax.ticklabel_format(style='plain', axis='y')
ax.yaxis.grid(True, linestyle='--', alpha=0.5)
ymin = int(df["price"].min() // 10 * 10)
ymax = int(df["price"].max() // 10 * 10 + 10)
ax.set_yticks(np.arange(ymin, ymax+1, 10))

# 雙Y軸右側
base = df["price"].iloc[0]
df["pct"] = (df["price"] - base) / base * 100
ax2 = ax.twinx()
ax2.set_ylabel("漲跌幅(%)", fontsize=12, fontproperties=myfont)
ax2.set_ylim((df["pct"].min(), df["pct"].max()))
ax2.yaxis.grid(False)

# 右側色彩
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

labels = []
for v in yticks:
    if v > 0:
        labels.append(f"+{v:.2f}%")
    else:
        labels.append(f"{v:.2f}%")

plt.tight_layout()
plt.savefig(OUT_PATH, bbox_inches='tight')
plt.close(fig)
print("圖已輸出:", OUT_PATH)
