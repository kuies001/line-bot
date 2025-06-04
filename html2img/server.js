const express = require('express');
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
// const axios = require("axios"); // 移除 axios 引用
const uuid = require('uuid');

const app = express();
const PORT = 3000;
const OUTPUT_DIR = "/shared";

// 確保輸出目錄存在
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    console.log(`Created output directory: ${OUTPUT_DIR}`);
} else {
    console.log(`Output directory already exists: ${OUTPUT_DIR}`);
}

// ✅ RPi5 環境專用：舊版 headless 模式 + chromium 路徑
async function getBrowser() {
  return await puppeteer.launch({
    headless: 'old',
    executablePath: '/usr/bin/chromium', // 或 '/usr/bin/chromium-browser'，取決於 Dockerfile 安裝的實際路徑
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--single-process',
      '--no-zygote',
      '--disable-web-security'
    ]
  });
}

// 📈 圖卡 API：GET /twse_card - **此端點已移除或不再用於生成盤子圖卡**
// 請移除或修改此端點，避免呼叫已失效的 Yahoo API
// 以下是註解掉的舊代碼，請移除
/*
app.get('/twse_card', async (req, res) => {
  let browser;
  try {
    console.log("Received request for /twse_card");
    // 這段抓取 Yahoo API 的程式碼將移到 Python 端
    // ... axios.get(...) ...
    // ... 處理數據 ...
    // ... 生成 HTML ...
    // ... 使用 Puppeteer 截圖並儲存 ...
    // ... 回傳檔案名稱 ...
    res.status(501).send("此端點功能已變更，請呼叫 /render 並傳遞 HTML"); // 返回 501 Not Implemented 或直接移除
  } catch (err) {
    console.error("🔥 Yahoo Finance 卡片生成錯誤：", err);
    res.status(500).json({ error: "產圖錯誤：" + err.message });
  } finally {
    if (browser) {
      await browser.close();
      console.log("Puppeteer browser closed.");
    }
  }
});
*/

// 🖼️ 萬用 HTML → 圖片轉換 API
app.use(express.text({ type: "*/*", limit: '5mb' }));
app.post('/render', async (req, res) => {
  const html = req.body;
  if (!html) {
      console.warn("Received POST /render request with empty body.");
      return res.status(400).send("❌ 沒收到 HTML 內容");
  }
  console.log(`Received POST /render request with HTML content (length: ${html.length}).`);

  let browser;
  try {
    browser = await getBrowser();
    const page = await browser.newPage();

    // 使用一個標準的 Viewport，但最終截圖尺寸由元素決定
    await page.setViewport({ width: 800, height: 600 }); // 可以稍微大一點，確保內容能完整渲染

    // 載入 HTML
    await page.setContent(html, { waitUntil: 'domcontentloaded' });

    // 等待指定的截圖目標元素出現
    const targetSelector = '#screenshot-target';
    try {
        console.log(`Waiting for selector: ${targetSelector}`);
        await page.waitForSelector(targetSelector, { timeout: 10000 }); // 等待目標元素最多 10 秒
        console.log(`Selector found: ${targetSelector}`);
    } catch (e) {
        console.error(`Timeout waiting for selector ${targetSelector} or selector not found.`, e);
        // 如果找不到目標元素，截整個頁面作為備用
        // throw new Error(`Required element with ID "${targetSelector}" not found in HTML.`);
         console.warn("Target element not found. Falling back to full page screenshot.");
         const buffer = await page.screenshot({ type: 'png', fullPage: true }); // 備用：截取整個頁面
         const filename = `render_fullpage_${uuid.v4()}.png`;
         const outputFile = path.join(OUTPUT_DIR, filename);
         fs.writeFileSync(outputFile, buffer);
         res.json({ filename: filename });
         return; // 處理完畢，返回
    }


    // 找到要截圖的元素
    const element = await page.$(targetSelector);
    if (!element) {
        // 理論上 waitForSelector 成功了這裡不應該找不到，但以防萬一
         console.error(`Element with selector ${targetSelector} found in DOM but cannot be queried.`);
         throw new Error(`Cannot query element with selector "${targetSelector}".`);
    }

    // 截取指定元素
    console.log(`Taking screenshot of element with selector: ${targetSelector}`);
    const buffer = await element.screenshot({ type: 'png' });
    console.log(`Screenshot taken for /render (buffer size: ${buffer.length} bytes).`);


    // 將圖片儲存到共享目錄
    const filename = `render_${uuid.v4()}.png`; // 使用 UUID 生成唯一檔案名稱
    const outputFile = path.join(OUTPUT_DIR, filename);
    fs.writeFileSync(outputFile, buffer);
    console.log(`Rendered image saved to: ${outputFile}`);

    // 回傳檔案名稱給呼叫者
     res.json({ filename: filename });
     console.log(`Sent JSON response for /render: { filename: "${filename}" }`);

  } catch (err) {
    console.error('🔥 HTML 轉圖錯誤:', err);
    res.status(500).json({ error: "轉圖失敗：" + err.message });
  } finally {
    if (browser) {
      await browser.close();
      console.log("Puppeteer browser closed for /render.");
    }
  }
});

app.listen(PORT, () => {
  console.log(`🚀 html2img server 已啟動：port ${PORT}`);
  console.log(`💾 Output directory mounted at: ${OUTPUT_DIR}`);
});