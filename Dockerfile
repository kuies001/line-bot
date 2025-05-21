# 最保險的基底，完整支援UTF-8、emoji、中文字型
FROM python:3.9

# 安裝 Playwright 所需的系統套件（重點！）
RUN apt-get update && apt-get install -y wget curl unzip \
    cron \
    supervisor \
    fonts-noto-cjk \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxss1 libasound2 \
    libxshmfence1 libgbm1 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt，先安裝依賴，加快build快取
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright + 下載 Chromium（這行很重要）
RUN pip install playwright && playwright install --with-deps

# 複製剩下的所有程式碼
COPY . .

# 設定環境變數（保險起見也留著）
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=Asia/Taipei

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "line_webhook_app:app"]
