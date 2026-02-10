# 快速啟動指南

## 🚀 升級亮點

此版本新增了強大的 Telegram Bot 互動功能，讓您可以：

1. **即時查詢** - 使用 `/now` 立即執行篩選
2. **歷史回測** - 使用 `/250209` 查詢過去任何一天的結果
3. **單幣診斷** - 使用 `/250209 ETHUSDT` 檢查特定幣種為何未入選

同時自動回推 ΔRS 歷史資料，解決首次運行 ΔRS 顯示 N/A 的問題。

---

## 📦 部署步驟

### 方法 1：Zeabur 部署（推薦）

1. **上傳專案到 GitHub**
   ```bash
   # 解壓縮後
   cd crypto-screener
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **在 Zeabur 建立專案**
   - 連接 GitHub Repository
   - 選擇 `crypto-screener` 專案
   - Zeabur 會自動偵測 Dockerfile 並建立容器

3. **（可選但推薦）添加 Volume 持久化儲存**
   
   **為什麼需要 Volume？**
   - 保存 ΔRS 歷史資料，避免重啟後重新回推
   - 保存 CSV 輸出檔案
   
   **如何添加？**
   - 在專案中點擊「Add Service」→「Volume」
   - 名稱：`crypto-data`
   - 大小：1GB（綽綽有餘）
   - 掛載路徑：`/app/data`
   
   **不添加會怎樣？**
   - 系統仍可正常運作！
   - 每次重啟會自動回推 30 天 ΔRS 歷史（約 1-2 分鐘）
   - 舊的 CSV 檔案會遺失（但不影響功能）

4. **設定環境變數**
   
   必要環境變數：
   ```
   BINANCE_API_KEY=你的幣安API_Key
   BINANCE_API_SECRET=你的幣安API_Secret
   TELEGRAM_BOT_TOKEN=你的Telegram_Bot_Token
   TELEGRAM_CHAT_ID=你的Chat_ID
   ```
   
   可選環境變數：
   ```
   TELEGRAM_ALLOWED_USERS=123456789,987654321  # 只允許特定用戶使用 Bot
   ```

4. **部署**
   - 點擊部署按鈕
   - 等待容器建立完成（約 1-2 分鐘）
   - 系統會自動啟動並開始運行

### 方法 2：Docker 本地部署

```bash
# 1. 解壓縮專案
unzip crypto-screener.zip
cd crypto-screener

# 2. 建立環境變數文件
cp .env.example .env
# 編輯 .env 填入真實值

# 3. 建立 Docker 映像
docker build -t crypto-screener .

# 4. 執行容器
docker run -d \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --name crypto-screener \
  --restart unless-stopped \
  crypto-screener

# 5. 查看日誌
docker logs -f crypto-screener
```

### 方法 3：本地直接運行

```bash
# 1. 解壓縮專案
unzip crypto-screener.zip
cd crypto-screener

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 設定環境變數
cp .env.example .env
# 編輯 .env 填入真實值

# 4. 執行
python main.py
```

---

## 🤖 Telegram Bot 使用

### 取得 Bot Token

1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot` 建立新 Bot
3. 按照提示設定 Bot 名稱
4. 複製取得的 Token

### 取得 Chat ID

1. 在 Telegram 搜尋 `@userinfobot`
2. 點擊 Start
3. Bot 會回傳您的 User ID（即 Chat ID）

### 開始使用

部署完成後，在 Telegram 中：

1. 搜尋並啟動您的 Bot
2. 發送 `/start` 查看可用命令
3. 發送 `/help` 查看詳細說明

---

## 📝 命令範例

### 立即執行篩選

```
/now
```

Bot 會回覆：
```
⏳ 正在執行篩選，請稍候...
```

約 2-5 分鐘後，會收到：
- 完整篩選報告
- TradingView 觀察清單檔案

### 回測查詢

```
/250209
```

查詢 2025/02/09 當日的篩選結果，使用該日已收盤的數據。

### 單幣種檢查

```
/250209 ETHUSDT
```

檢查 ETHUSDT 在 2025/02/09 是否入選：

**入選範例：**
```
✅ ETHUSDT 檢查結果
日期：2025/02/09

入選！排名第 3 名
最終評分：81.5

RS 強度：
  • RS(7): 92.3%
  • RS(21): 76.1%

T 值：
  • T(20): 0.0234
  • T(20) 百分位: 68.5%
  • S(N): 15.2
```

**未入選範例：**
```
❌ ETHUSDT 檢查結果
日期：2025/02/09

未入選

檢查清單：
✅ 數據載入
✅ 基礎過濾
✅ RS Rank 篩選
    RS(7): 92.3% RS(21): 76.1%
❌ T 值篩選
    S(N): -3.5

失敗原因：
未通過 T 值篩選：S(N) = -3.5 ≤ 0（非上升趨勢）
```

---

## ⚙️ 重要配置說明

### config.py 關鍵參數

```python
# ΔRS 自動回推（新功能）
AUTO_BACKFILL_RS_HISTORY = True  # 啟動時自動回推
RS_HISTORY_BACKFILL_DAYS = 30    # 回推 30 天

# Telegram Bot 命令
COMMAND_TIMEOUT = 300            # 命令執行超時（5 分鐘）
BACKTEST_MAX_DAYS = 0            # 回測查詢天數上限（0 = 不限）

# 排程設定
SCHEDULE_HOUR = 8                # 每日 08:00 執行
SCHEDULE_MINUTE = 0
RUN_ON_STARTUP = False           # 建議設為 False，避免部署時立即執行
```

### 權限控制（可選）

限制只有特定用戶可使用 Bot：

```bash
# 在 Zeabur 環境變數中設定
TELEGRAM_ALLOWED_USERS=123456789,987654321

# 或在 .env 中設定
TELEGRAM_ALLOWED_USERS=123456789,987654321
```

若不設定此變數，則所有人都可使用 Bot（不推薦）。

---

## 🔧 常見問題

### Q1: 如何取得我的 Telegram User ID？

A: 在 Telegram 搜尋 `@userinfobot`，點擊 Start，Bot 會顯示您的 ID。

### Q2: ΔRS 仍然顯示 N/A 怎麼辦？

A: 確認 `config.py` 中 `AUTO_BACKFILL_RS_HISTORY = True`，重啟系統後會自動回推。

### Q3: 回測查詢為什麼比實時篩選慢？

A: 回測需要重新拉取所有幣種的歷史數據，且使用 `endTime` 參數確保不偷看未來，因此較慢。

### Q4: 可以同時使用多個 Chat ID 嗎？

A: 定時推送只支援單一 `TELEGRAM_CHAT_ID`，但 Bot 命令可被所有有權限的用戶使用。

### Q5: Zeabur 部署時，容器重啟後 ΔRS 資料會消失嗎？

A: 有兩種情況：

**情況 1：已添加 Volume（推薦）**
- ΔRS 歷史資料會持久化保存
- 重啟後立即可用，無需等待

**情況 2：未添加 Volume**
- 重啟後 ΔRS 歷史會清空
- 系統會自動回推過去 30 天的資料（約 1-2 分鐘）
- 功能完全正常，只是首次啟動稍慢

**如何添加 Zeabur Volume？**
1. 在專案中點擊「Add Service」→「Volume」
2. 名稱：`crypto-data`，大小：1GB
3. 在服務設定中，將 Volume 掛載到 `/app/data`
4. 重新部署即可

### Q6: Docker 本地部署時如何持久化資料？

A: 使用 `-v` 參數掛載數據卷：

```bash
docker run -d \
  --env-file .env \
  -v $(pwd)/data:/app/data \  # 重點在這行
  --name crypto-screener \
  --restart unless-stopped \
  crypto-screener
```

這樣 `/app/data` 目錄的內容會保存在宿主機的 `./data` 目錄中。

### Q7: 如何查看系統日誌？

Zeabur:
- 在專案頁面點擊「Logs」查看即時日誌

Docker:
```bash
docker logs -f crypto-screener
```

本地運行:
- 日誌會輸出到終端（stdout）

---

## 🎯 最佳實踐

1. **首次部署**
   - 設定 `RUN_ON_STARTUP = False`，避免部署時立即執行
   - 手動使用 `/now` 測試系統是否正常

2. **權限控制**
   - 強烈建議設定 `TELEGRAM_ALLOWED_USERS`
   - 避免陌生人濫用您的 API 配額

3. **數據持久化**
   - Docker 部署時務必掛載 `/app/data` 卷
   - 確保 ΔRS 歷史不會因重啟而消失

4. **監控與維護**
   - 定期檢查日誌確認系統正常運行
   - 若 API Rate Limit 頻繁觸發，可調整 `API_REQUEST_DELAY`

---

## 📞 技術支援

- GitHub Issues: 提交問題或建議
- Telegram: 在 Bot 中發送 `/help` 查看使用說明

祝您使用順利！🚀
