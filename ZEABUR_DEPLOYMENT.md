# Zeabur 部署完整指南

## 📋 部署前準備

### 1. 準備 API 憑證

#### 幣安 API
1. 登入幣安帳戶
2. 前往「API 管理」
3. 建立新的 API Key
4. **重要：** 只需開啟「讀取」權限（不需要交易權限）
5. 複製 API Key 和 Secret（妥善保管）

#### Telegram Bot
1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot` 建立新 Bot
3. 設定 Bot 名稱和使用者名稱
4. 複製取得的 Bot Token

#### Telegram Chat ID
1. 在 Telegram 搜尋 `@userinfobot`
2. 點擊 Start
3. 複製您的 User ID（這就是 Chat ID）

---

## 🚀 Zeabur 部署步驟

### 步驟 1：準備 GitHub Repository

```bash
# 1. 解壓縮專案
unzip crypto-screener.zip
cd crypto-screener

# 2. 初始化 Git（若尚未初始化）
git init

# 3. 添加所有檔案
git add .

# 4. 提交
git commit -m "Initial commit: Crypto screener v2.0"

# 5. 連接到您的 GitHub Repository
git remote add origin https://github.com/your-username/crypto-screener.git

# 6. 推送到 GitHub
git branch -M main
git push -u origin main
```

### 步驟 2：在 Zeabur 建立專案

1. **登入 Zeabur**
   - 前往 [zeabur.com](https://zeabur.com)
   - 使用 GitHub 帳號登入

2. **建立新專案**
   - 點擊「New Project」
   - 選擇 Region（建議選擇離您較近的區域）

3. **部署服務**
   - 點擊「Add Service」
   - 選擇「Git」
   - 授權 Zeabur 訪問您的 GitHub
   - 選擇 `crypto-screener` Repository
   - Zeabur 會自動偵測 Dockerfile

### 步驟 3：添加 Volume（可選但推薦）

**為什麼需要 Volume？**
- 保存 ΔRS 歷史資料
- 避免容器重啟後需要重新回推（節省 1-2 分鐘啟動時間）
- 保存每日的 CSV 輸出檔案

**如何添加？**

1. **在專案中添加 Volume**
   - 點擊「Add Service」
   - 選擇「Volume」
   - 設定參數：
     ```
     名稱：crypto-data
     大小：1 GB
     ```
   - 點擊「Create」

2. **掛載 Volume 到服務**
   - 點擊您的 `crypto-screener` 服務
   - 找到「Volumes」或「Storage」選項
   - 點擊「Add Volume」
   - 設定：
     ```
     Volume：選擇剛建立的 crypto-data
     掛載路徑：/app/data
     ```
   - 儲存設定

**不添加 Volume 會怎樣？**
- ✅ 系統仍可完全正常運作
- ⚠️ 每次重啟需要 1-2 分鐘自動回推 ΔRS 歷史
- ⚠️ 舊的 CSV 檔案會遺失（但不影響篩選功能）

### 步驟 4：設定環境變數

1. **進入服務設定**
   - 點擊您的 `crypto-screener` 服務
   - 找到「Variables」或「環境變數」選項

2. **添加必要環境變數**
   
   點擊「Add Variable」，依次添加：

   | 變數名稱 | 值 | 說明 |
   |---------|-----|------|
   | `BINANCE_API_KEY` | 您的幣安 API Key | 必要 |
   | `BINANCE_API_SECRET` | 您的幣安 API Secret | 必要 |
   | `TELEGRAM_BOT_TOKEN` | 您的 Bot Token | 必要 |
   | `TELEGRAM_CHAT_ID` | 您的 Chat ID | 定時推送用（必要） |
   | `TELEGRAM_ALLOWED_USERS` | `123456789,987654321` | 白名單（可選） |

3. **（可選）調整其他設定**
   
   若需要修改預設行為，可添加：

   | 變數名稱 | 預設值 | 說明 |
   |---------|--------|------|
   | `SCHEDULE_HOUR` | `8` | 每日執行的小時（GMT+8） |
   | `RUN_ON_STARTUP` | `False` | 啟動時是否立即執行 |
   | `RS_HISTORY_BACKFILL_DAYS` | `30` | ΔRS 回推天數 |

### 步驟 5：部署

1. **觸發部署**
   - Zeabur 會在您推送代碼到 GitHub 時自動部署
   - 或手動點擊「Redeploy」

2. **等待建置完成**
   - 首次建置約需 2-3 分鐘
   - 可在「Logs」中查看建置進度

3. **確認服務狀態**
   - 等待狀態變為「Running」
   - 綠色燈號表示服務正常運行

### 步驟 6：測試系統

1. **在 Telegram 測試 Bot**
   ```
   發送：/start
   回應：歡迎訊息和命令列表
   
   發送：/help
   回應：詳細使用說明
   
   發送：/now
   回應：⏳ 正在執行篩選...
   等待 2-5 分鐘後收到完整報告
   ```

2. **檢查日誌**
   - 在 Zeabur 控制台點擊「Logs」
   - 確認看到：
     ```
     加密貨幣強勢幣篩選系統啟動
     環境變數驗證通過
     Telegram Bot 初始化成功
     排程器已設定：每日 08:00
     Telegram Bot 開始輪詢...
     ```

---

## 🔧 常見問題排查

### 問題 1：容器一直重啟

**可能原因：**
- 環境變數缺失或錯誤

**解決方法：**
1. 檢查 Logs，找到錯誤訊息
2. 確認所有必要環境變數已設定
3. 檢查 API Key 是否正確（無多餘空格）

### 問題 2：Bot 無回應

**可能原因：**
- Bot Token 錯誤
- 未授權（設定了 `TELEGRAM_ALLOWED_USERS` 但您的 ID 不在其中）

**解決方法：**
1. 確認 `TELEGRAM_BOT_TOKEN` 正確
2. 檢查 Logs 中是否有 "⛔ 您沒有權限" 的訊息
3. 若有白名單，確認您的 User ID 在內

### 問題 3：定時任務未執行

**檢查方式：**
1. 查看 Logs，在設定的時間（預設 08:00 GMT+8）是否有執行記錄
2. 確認 `TELEGRAM_CHAT_ID` 已設定

**解決方法：**
- 若未執行，檢查 `SCHEDULE_HOUR` 和 `SCHEDULE_MINUTE` 設定
- 注意時區為 GMT+8（台北時間）

### 問題 4：記憶體或 CPU 不足

**症狀：**
- 容器頻繁重啟
- 篩選執行到一半失敗

**解決方法：**
1. 在 Zeabur 服務設定中提升資源配額
2. 調整 `API_REQUEST_DELAY`（延長間隔以降低負載）

---

## 📊 監控與維護

### 日誌監控

**重要日誌關鍵字：**
- ✅ `篩選流程執行完成` - 成功
- ⚠️ `rate limit` - API 限制（可能需要調整延遲）
- ❌ `篩選系統錯誤` - 嚴重錯誤

### 定期檢查

建議每週檢查：
1. 定時任務是否正常執行
2. Telegram 推送是否成功
3. Volume 使用量（若接近上限則擴容）

### 更新部署

當您修改代碼後：
```bash
git add .
git commit -m "Update: description"
git push
```

Zeabur 會自動觸發重新部署。

---

## 💡 最佳實踐

### 安全性

1. **API 權限最小化**
   - 幣安 API 只開啟「讀取」權限
   - 絕不開啟「交易」權限

2. **Bot 權限控制**
   - 務必設定 `TELEGRAM_ALLOWED_USERS`
   - 避免陌生人濫用您的 API 配額

3. **環境變數保護**
   - 絕不將 API Key 提交到 GitHub
   - 只在 Zeabur 控制台設定

### 效能優化

1. **首次部署**
   - 設定 `RUN_ON_STARTUP = False`
   - 避免部署時立即執行導致超時

2. **API Rate Limit**
   - 若頻繁觸發限制，調整 `API_REQUEST_DELAY` 到 0.2 或更高

3. **Volume 使用**
   - 建議啟用 Volume
   - 避免每次重啟都回推歷史

### 成本控制

1. **Volume 大小**
   - 1GB 足夠使用數個月
   - 不需要設定過大

2. **資源配額**
   - 預設配額足以運行
   - 除非遇到問題，否則不需提升

---

## 🎯 下一步

部署完成後：

1. ✅ 測試所有 Bot 命令
2. ✅ 確認定時推送正常
3. ✅ 加入監控和告警（可選）
4. ✅ 開始享受自動化篩選服務！

有任何問題請參考主要文件或提交 GitHub Issue。
