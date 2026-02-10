# 加密貨幣強勢幣篩選系統

一個自動化的加密貨幣篩選系統，每日從幣安 U 本位永續合約市場中篩選出具有中波段（3–14 天）大幅上漲潛力的強勢幣候選清單，並透過 Telegram Bot 推送結果。

## 功能特點

- **雙框架整合**：結合 RS Rank（相對強度排名）與 T 值（趨勢品質量化）兩套分析框架
- **加權評分模型**：綜合多維度指標進行量化評分
- **自動化運行**：支援 Zeabur/Docker 容器化部署，每日定時執行
- **Telegram Bot 互動**：
  - `/now` - 立即執行一次完整篩選
  - `/YYMMDD` - 回測查詢指定日期的篩選結果
  - `/YYMMDD SYMBOL` - 檢查特定幣種是否入選，顯示詳細檢查清單
- **自動推送**：每日定時推送篩選結果與 TradingView 觀察清單
- **ΔRS 自動回推**：啟動時自動回推過去 30 天的 RS 排名歷史，避免 ΔRS 顯示 N/A
- **完整錯誤處理**：確保系統穩定運行，不會因單一錯誤而崩潰

## 篩選邏輯

系統採用多層漏斗式篩選：

```
全市場幣種
    ↓
【基礎過濾】
- 上線天數 ≥ 30 天
- 7 日成交量中位數 > 100,000 USD
- 數據完整性檢查
    ↓
【RS Rank 篩選】
- RS(7) 百分位 ≥ 85%
- RS(21) 百分位 ≥ 70%
- RS(7) > RS(21)（動量加速）
    ↓
【T 值篩選】
- S(N) > 0（上升趨勢）
- T(20) 百分位 ≥ 50%
    ↓
【加權評分】
- RS 短期強度（25%）
- 趨勢品質（20%）
- 成交量加速（20%）
- 動量加速度（20%）
- 波動率展開（10%）
- BTC 低相關性（5%）
    ↓
最終候選清單
```

## 快速開始

### 本地運行

1. **Clone 專案**
```bash
git clone <your-repo-url>
cd crypto-screener
```

2. **安裝依賴**
```bash
pip install -r requirements.txt
```

3. **配置環境變數**
```bash
cp .env.example .env
# 編輯 .env 填入真實的 API Key 和 Telegram Token
```

4. **執行程式**
```bash
python main.py
```

### Zeabur 部署

1. **連接 GitHub Repo**
   - 在 Zeabur 控制台選擇「從 GitHub 部署」
   - 選擇此專案的 Repository

2. **（可選）添加 Volume 實現數據持久化**
   - 點擊「Add Service」→「Volume」
   - 設定名稱：`crypto-data`，大小：1GB
   - 在服務設定中，將 Volume 掛載到 `/app/data`
   - **若不掛載：** 系統會在每次重啟時自動回推 ΔRS 歷史（1-2 分鐘）

3. **設定環境變數**
   - 在 Zeabur 專案設定中，新增以下環境變數：
     - `BINANCE_API_KEY`：幣安 API Key
     - `BINANCE_API_SECRET`：幣安 API Secret
     - `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
     - `TELEGRAM_CHAT_ID`：Telegram Chat ID（用於定時推送）
     - `TELEGRAM_ALLOWED_USERS`：（可選）允許使用 Bot 的用戶 ID，逗號分隔

4. **部署**
   - 點擊部署，Zeabur 會自動建立容器並啟動服務
   - 系統將在每日 08:00（GMT+8）自動執行篩選

### Docker 本地部署

```bash
# 建立映像
docker build -t crypto-screener .

# 執行容器
docker run -d \
  -e BINANCE_API_KEY="your_key" \
  -e BINANCE_API_SECRET="your_secret" \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e TELEGRAM_CHAT_ID="your_chat_id" \
  --name crypto-screener \
  crypto-screener
```

## Telegram Bot 命令使用

系統支援以下 Telegram Bot 命令：

### `/now` - 立即執行篩選

立即執行一次完整的篩選流程，約需 2-5 分鐘。

```
/now
```

Bot 會回傳：
- 完整的篩選報告（包含評分、RS、T 值等）
- TradingView 觀察清單檔案（可直接匯入）

### `/YYMMDD` - 回測查詢

查詢指定日期的篩選結果（不偷看未來數據）。

```
/250209    # 查詢 2025/02/09
/250131    # 查詢 2025/01/31
```

**特點：**
- 使用 GMT+8 時區
- 只使用截止到該日收盤的數據
- 查詢範圍取決於幣安 API 可用的歷史數據
- 回測結果不含 ΔRS（排名變化速度）

### `/YYMMDD SYMBOL` - 單幣種檢查

檢查特定幣種在指定日期是否入選，若未入選會顯示詳細檢查清單。

```
/250209 ETHUSDT    # 檢查 ETHUSDT 在 2025/02/09 是否入選
/250209 ETH        # 自動補上 USDT
```

Bot 會回傳：

**入選時：**
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

**未入選時：**
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

**權限控制（可選）：**

若設定 `TELEGRAM_ALLOWED_USERS` 環境變數，只有白名單中的用戶可使用 Bot。

```bash
# 允許多個用戶（用戶 ID 可從 Telegram 取得）
TELEGRAM_ALLOWED_USERS="123456789,987654321"
```

## 參數調整

所有可調參數集中在 `config.py` 中，主要參數說明：

### 排程設定
- `SCHEDULE_HOUR`：每日執行的小時（預設 8）
- `SCHEDULE_MINUTE`：每日執行的分鐘（預設 0）
- `TIMEZONE`：時區（預設 "Asia/Taipei"）

### 基礎過濾
- `MIN_LISTING_DAYS`：最小上線天數（預設 30）
- `MIN_MEDIAN_VOLUME`：最小成交量中位數（預設 100,000 USD）
- `MAX_MISSING_CANDLES`：允許缺失的 K 線數量（預設 2）

### RS Rank
- `RS_SHORT_WINDOW`：短期窗口（預設 7 天）
- `RS_LONG_WINDOW`：長期窗口（預設 21 天）
- `RS_SHORT_THRESHOLD`：短期百分位門檻（預設 85）
- `RS_LONG_THRESHOLD`：長期百分位門檻（預設 70）

### T 值
- `T_MA_PERIOD`：移動平均週期（預設 5）
- `T_MAIN_WINDOW`：主窗口大小（預設 20）
- `T_SHORT_WINDOW`：輔助窗口大小（預設 10）
- `T_THRESHOLD`：T 值百分位門檻（預設 50）

### 評分權重
可在 `SCORE_WEIGHTS` 字典中調整各維度的權重：
```python
SCORE_WEIGHTS = {
    "rs7": 0.25,    # RS 短期強度
    "t20": 0.20,    # 趨勢品質
    "vol": 0.20,    # 成交量加速
    "drs": 0.20,    # 動量加速度
    "atr": 0.10,    # 波動率展開
    "corr": 0.05,   # BTC 低相關性
}
```

## 輸出範例

### Telegram 訊息

```
📊 強勢幣篩選報告 2025-02-09

掃描範圍：幣安 U 本位永續合約
通過基礎過濾：245 個
通過 RS 篩選：38 個
通過 T 值篩選：22 個
最終候選：22 個

排名 | 幣種 | 評分 | RS(7) | T(20) | 量比 | ΔRS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ETHUSDT   85.2  95%  72%  3.1x  +12 🟢
2. SOLUSDT   81.7  91%  68%  2.5x  +8  ⚡
3. BNBUSDT   78.3  88%  65%  2.0x  +5

標記說明：
🟢 = 趨勢品質穩定（T(10) 未衰減）
⚡ = 波動率突破（從壓縮展開）
```

### TradingView 觀察清單檔案

```
BINANCE:ETHUSDT.P
BINANCE:SOLUSDT.P
BINANCE:BNBUSDT.P
```

可直接匯入 TradingView 的觀察清單功能。

## 專案結構

```
crypto-screener/
├── main.py                 # 程式進入點
├── config.py              # 參數配置（唯一需要修改的檔案）
├── requirements.txt       # 依賴清單
├── .env.example          # 環境變數範本
├── .gitignore            # Git 忽略規則
├── README.md             # 專案說明
├── screener/             # 篩選邏輯模組
│   ├── data.py           # 數據拉取與前處理
│   ├── filters.py        # 基礎過濾
│   ├── rs_rank.py        # RS Rank 計算
│   ├── t_value.py        # T 值計算
│   └── scoring.py        # 評分模型
├── bot/                  # Telegram 推送模組
│   └── telegram.py
└── utils/                # 工具函式
    └── logger.py         # 日誌與脫敏
```

## 重要提醒

⚠️ **此系統產出的是候選觀察清單，不是買入信號**

- 篩選結果應作為進一步分析的起點，而非直接交易依據
- 建議結合其他技術分析工具和風險管理策略
- 熊市中候選清單可能為空，這是正常現象
- 回測結果需注意存活偏差（Survivorship Bias）

## 技術實作細節

### RS Rank（相對強度排名）

以 BTC 作為基準，計算差值形式的相對強度：

```
RS_diff(n) = 幣種 n 天報酬率 - BTC n 天報酬率
```

使用雙窗口（7 天 + 21 天）捕捉不同時間尺度的動量。

### T 值（趨勢品質量化）

1. **標準化**：將價格序列轉換為離散位移路徑
2. **T1**：基於連續波段的品質量化
3. **T2**：基於絕對波動區間的遞迴拆解
4. **T 值**：`T = max(T1, T2) / N^(3/2)`

只保留 S(N) > 0（上升趨勢）的幣種。

### 異常值處理

- 計算 ATR(14)
- 若單根 K 線漲跌幅 > 4 × ATR(14)，標記為異常
- 異常 K 線在 T 值計算中，σ(k) 強制設為 0

## 常見問題

**Q: 為什麼今天沒有推送結果？**

A: 可能原因：
1. 當日無符合條件的幣種（熊市常見）
2. 系統發生錯誤（檢查 Zeabur 日誌）
3. Telegram Token 或 Chat ID 配置錯誤

**Q: 如何調整篩選條件更嚴格/寬鬆？**

A: 修改 `config.py` 中的門檻參數：
- 更嚴格：提高 `RS_SHORT_THRESHOLD`、`RS_LONG_THRESHOLD`、`T_THRESHOLD`
- 更寬鬆：降低上述門檻值

**Q: 歷史排名數據（ΔRS）遺失怎麼辦？**

A: 容器重啟後，若 `data/` 目錄被清空，ΔRS 會顯示為 N/A。這不影響其他計算，系統會自動開始累積新的歷史數據。

**Q: 可以增加其他交易所嗎？**

A: 當前版本僅支援幣安。如需其他交易所，需修改 `screener/data.py` 中的數據拉取邏輯。

## 授權

此專案僅供學習和研究使用。使用本系統進行實際交易的風險由使用者自行承擔。

## 回饋與貢獻

如有問題或建議，請透過 GitHub Issues 或 Telegram 聯繫。
