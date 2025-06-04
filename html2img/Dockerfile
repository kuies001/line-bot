# 選擇一個 Node.js 基礎映像檔
FROM node:20-bookworm-slim

# 設定工作目錄
WORKDIR /app

# 複製 package.json 和 package-lock.json (或 yarn.lock)
COPY package*.json ./

# 安裝 Node.js 相依模組
RUN npm install

# 安裝 chromium、必要的函式庫 和 中文字體
RUN apt-get update && \
    # 確保 sources.list 包含 main contrib non-free
    echo "deb http://deb.debian.org/debian/ bookworm main contrib non-free" > /etc/apt/sources.list.d/bookworm_main_contrib_non-free.list && \
    echo "deb http://deb.debian.org/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list.d/bookworm_main_contrib_non-free.list && \
    echo "deb http://deb.debian.org/debian-security/ bookworm-security main contrib non-free" >> /etc/apt/sources.list.d/bookworm_main_contrib_non-free.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    chromium \
    fontconfig \
    libfreetype6 \
    libharfbuzz0b \
    libfontconfig1 \
    libatk1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libappindicator3-1 \
    libnss3 \
    libasound2 \
    libexpat1 \
    libdbus-1-3 \
    libgbm1 \
    libicu-dev \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libwebpdemux2 \
    libwoff1 \
    libopus0 \
    libvpx7 \
    libenchant-2-2 \
    libegl1 \
    libgles2 \
    libevent-core-2.1-7 \
    libsecret-1-0 \
    libglib2.0-0 \
    libpangoft2-1.0-0 \
    libsqlite3-0 \
    libstdc++6 \
    libsystemd0 \
    libudev1 \
    libwayland-client0 \
    libwayland-egl1 \
    libwayland-cursor0 \
    libxkbcommon0 \
    xz-utils \
    # === 新增：安裝更多中文字體套件 ===
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-wqy-zenhei \
    fonts-arphic-ukai \
    fonts-arphic-uming && \
    # ==================================
    # 更新字體快取
    fc-cache -fv && \
    # 清理 APT 快取
    rm -rf /var/lib/apt/lists/*

# 複製應用程式碼到容器中
COPY . .

# 定義容器啟動時執行的命令
CMD ["node", "server.js"]