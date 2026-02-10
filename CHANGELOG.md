# 更新日誌

## v2.0.0 - 2025-02-09

### 重大更新：Telegram Bot 互動功能

#### 新增功能

1. **Telegram Bot 命令支援**
   - `/now` - 立即執行一次完整篩選
   - `/YYMMDD` - 回測查詢指定日期的篩選結果
   - `/YYMMDD SYMBOL` - 檢查特定幣種是否入選，顯示詳細檢查清單

2. **ΔRS 自動回推**
   - 系統啟動時自動回推過去 30 天的 RS 排名歷史
   - 避免首次運行時 ΔRS 顯示 N/A
   - 可在 `config.py` 中配置 `AUTO_BACKFILL_RS_HISTORY` 和 `RS_HISTORY_BACKFILL_DAYS`

3. **回測功能**
   - 支援查詢歷史特定日期的篩選結果
   - 使用 Binance API `endTime` 參數確保不偷看未來數據
   - 單幣種檢查功能，顯示未通過原因和詳細數據

4. **Docker 支援**
   - 新增 `Dockerfile` 和 `.dockerignore`
   - 支援 Docker 容器化部署
   - 優化映像大小和建構速度

#### 改進

1. **非同步架構**
   - 主程式改用 `asyncio` 架構
   - 排程器與 Telegram Bot 同時運行
   - 命令執行不阻塞定時任務

2. **權限控制**
   - 新增 `TELEGRAM_ALLOWED_USERS` 環境變數
   - 支援白名單機制限制 Bot 使用權限

3. **錯誤處理**
   - 增強回測功能的錯誤處理
   - 命令執行超時保護（300 秒）
   - 更詳細的錯誤訊息

#### 技術細節

- `screener/backtest.py` - 新增回測引擎
- `screener/rs_rank.py` - 新增 `backfill_history()` 方法
- `bot/telegram.py` - 重構為支援命令處理的雙向互動 Bot
- `main.py` - 重構為非同步架構，整合排程器與 Bot

#### 配置變更

新增配置項：
- `TELEGRAM_ALLOWED_USERS` - Bot 權限控制
- `AUTO_BACKFILL_RS_HISTORY` - 是否自動回推 RS 歷史
- `RS_HISTORY_BACKFILL_DAYS` - 回推天數（預設 30）
- `COMMAND_TIMEOUT` - 命令執行超時時間（預設 300 秒）
- `BACKTEST_MAX_DAYS` - 回測查詢天數上限（預設 0，不限）

#### 部署注意事項

1. **Zeabur 部署**
   - 確保環境變數已正確設定
   - 新增 `TELEGRAM_ALLOWED_USERS`（可選）

2. **Docker 部署**
   - 使用 `docker build -t crypto-screener .` 建立映像
   - 透過 `-e` 參數注入環境變數

3. **向後兼容**
   - 原有的定時推送功能完全保留
   - 不影響現有配置和篩選邏輯
   - 所有篩選條件與評分模型維持不變

---

## v1.0.0 - 2025-02-09

### 初始版本

- RS Rank（相對強度排名）計算
- T 值（趨勢品質量化）計算
- 加權評分模型
- 基礎過濾與異常值處理
- 每日定時執行與 Telegram 推送
- TradingView 觀察清單生成
