# 數據持久化方案說明

## 🎯 核心概念

在 Zeabur 等容器化平台上，容器的檔案系統是**暫時性的**：
- 容器重啟時，檔案系統會重置
- `/app/data` 目錄中的所有檔案會消失
- 需要持久化儲存來保存資料

---

## 📊 兩種方案對比

### 方案 A：添加 Zeabur Volume（推薦）

```
┌─────────────────────────────────────────┐
│  Zeabur 容器                              │
│                                          │
│  /app/data/                              │
│  ├── rs_rank_history.json  ←──┐        │
│  └── results/                 │         │
│      ├── screener_2025-02-09.csv        │
│      └── watchlist_2025-02-09.txt       │
│                                │         │
└─────────────────────────────────┼────────┘
                                 │
                    掛載 Volume   │
                                 ↓
┌─────────────────────────────────────────┐
│  Zeabur Volume (持久化儲存)               │
│                                          │
│  永久保存，重啟不會消失                    │
│  容量：1 GB                               │
└─────────────────────────────────────────┘
```

**優點：**
- ✅ 資料永久保存
- ✅ 重啟後立即可用
- ✅ 保留歷史 CSV 檔案
- ✅ 無需等待回推

**缺點：**
- ⚠️ 需要額外設定（但很簡單）
- ⚠️ 可能有額外費用（通常很便宜）

**設定步驟：**
1. Zeabur 控制台 → Add Service → Volume
2. 名稱：`crypto-data`，大小：1 GB
3. 在服務設定中，掛載到 `/app/data`

---

### 方案 B：不掛載 Volume（極簡方案）

```
┌─────────────────────────────────────────┐
│  Zeabur 容器                              │
│                                          │
│  /app/data/                              │
│  ├── (空的，每次重啟後清空)                │
│  └── ...                                 │
│                                          │
│  ⚙️ 啟動時自動執行：                       │
│  backfill_history()                      │
│  └─ 回推過去 30 天的 RS 排名              │
│     (約 1-2 分鐘)                         │
└─────────────────────────────────────────┘
```

**優點：**
- ✅ 無需任何額外設定
- ✅ 零成本
- ✅ 系統自動處理一切
- ✅ 功能完全正常

**缺點：**
- ⚠️ 每次重啟需 1-2 分鐘回推
- ⚠️ 舊的 CSV 檔案會遺失

**運作原理：**
```python
# main.py 中的邏輯
def run_screener_sync():
    # ...
    rs_calculator = RSRankCalculator(btc_df)
    
    # ★ 自動檢查並回推歷史
    if config.AUTO_BACKFILL_RS_HISTORY:
        rs_calculator.backfill_history(filtered_data)
    # ...
```

---

## 🔍 詳細流程說明

### 方案 A 的運作流程

```
容器啟動
  ↓
檢查 /app/data/rs_rank_history.json
  ↓
存在（因為掛載了 Volume）
  ↓
直接載入歷史資料 ✅
  ↓
系統立即可用
```

### 方案 B 的運作流程

```
容器啟動
  ↓
檢查 /app/data/rs_rank_history.json
  ↓
不存在（容器重啟後檔案系統重置）
  ↓
觸發自動回推 (backfill_history)
  ↓
遍歷所有通過基礎過濾的幣種
  ↓
計算過去 30 天每一天的 RS(7) 百分位
  ↓
保存到 rs_rank_history.json
  ↓
回推完成（耗時 1-2 分鐘） ✅
  ↓
系統可用，ΔRS 正常顯示
```

---

## 💾 數據內容說明

### rs_rank_history.json 結構

```json
{
  "2025-02-09": {
    "BTCUSDT": 50.0,
    "ETHUSDT": 85.3,
    "SOLUSDT": 92.1,
    ...
  },
  "2025-02-08": {
    "BTCUSDT": 48.5,
    "ETHUSDT": 82.7,
    ...
  },
  ...
}
```

- **用途：** 計算 ΔRS（排名變化速度）
- **大小：** 約 100-500 KB
- **保留天數：** 最近 30 天（自動清理舊資料）

### CSV 結果檔案

```
data/results/
├── screener_2025-02-09.csv
├── screener_2025-02-08.csv
├── watchlist_2025-02-09.txt
└── ...
```

- **用途：** 歷史記錄，方便回溯
- **是否必要：** 否（系統功能不依賴這些檔案）

---

## 🤔 如何選擇？

### 選擇方案 A（添加 Volume）如果：
- ✅ 您希望保留完整的歷史記錄
- ✅ 您不介意多花 1-2 分鐘設定
- ✅ 您的 Zeabur 計畫包含免費 Volume 額度
- ✅ 您預期容器會頻繁重啟

### 選擇方案 B（不掛載）如果：
- ✅ 您想要最簡單的部署方式
- ✅ 您不需要保留歷史 CSV
- ✅ 容器重啟不頻繁（一個月可能只有幾次）
- ✅ 您可以接受重啟後等待 1-2 分鐘

---

## 🎯 我們的建議

### 初學者 / 快速測試
→ **方案 B（不掛載）**
- 先體驗系統功能
- 之後再決定是否需要 Volume

### 長期穩定使用
→ **方案 A（添加 Volume）**
- 一次設定，永久受益
- 更好的用戶體驗

---

## 📝 實際操作範例

### Zeabur Volume 設定（方案 A）

**步驟 1：建立 Volume**
1. 進入專案頁面
2. 點擊「Add Service」
3. 選擇「Volume」
4. 填寫：
   ```
   名稱：crypto-data
   大小：1
   單位：GB
   ```
5. 點擊「Create」

**步驟 2：掛載 Volume**
1. 點擊您的 `crypto-screener` 服務
2. 找到「Volumes」或「Storage」設定
3. 點擊「Mount Volume」或「Add Volume」
4. 選擇：
   ```
   Volume：crypto-data
   掛載路徑：/app/data
   讀寫權限：Read/Write
   ```
5. 儲存並重新部署

**完成！** 之後所有寫入 `/app/data` 的資料都會持久化。

---

## 🔧 驗證方法

### 如何確認 Volume 是否生效？

**方法 1：檢查日誌**

有 Volume：
```
已保存 RS 排名歷史到 ./data/rs_rank_history.json
[不會看到 "開始回推 RS 歷史排名資料"]
```

無 Volume（首次啟動）：
```
開始回推 RS 歷史排名資料...
需要回推 30 天的 RS 排名
RS 歷史排名回推完成，共回推 30 天
```

**方法 2：使用 Bot 命令**

在 Telegram 發送 `/now`：
- 有 Volume：ΔRS 欄位顯示數字（如 +8, -3）
- 無 Volume（首次）：ΔRS 顯示 N/A
- 無 Volume（回推後）：ΔRS 顯示數字

---

## ❓ 常見問題

### Q: Volume 會增加成本嗎？
A: 大多數 Zeabur 計畫包含一定的免費 Volume 額度。1GB Volume 通常在免費額度內，或每月只需幾美元。

### Q: 不用 Volume，ΔRS 永遠是 N/A 嗎？
A: 不是！系統會自動回推 30 天歷史。回推完成後，ΔRS 就能正常顯示。只是每次容器重啟都需要重新回推一次。

### Q: 回推需要多久？
A: 約 1-2 分鐘。期間系統其他功能（如 Bot 命令）仍可使用。

### Q: 可以中途添加 Volume 嗎？
A: 可以！隨時都能添加 Volume 並掛載，不會影響現有功能。

### Q: Volume 滿了怎麼辦？
A: 系統會自動清理 30 天前的歷史資料。1GB 足夠使用數年。若真的滿了，可在 Zeabur 控制台直接擴容。

---

## 🎓 技術細節（進階）

### ΔRS 回推演算法

```python
def backfill_history(self, data_dict):
    """自動回推過去 N 天的 RS 排名"""
    
    # 1. 讀取現有歷史
    history = self.load_history()
    
    # 2. 找出缺失的日期
    for i in range(backfill_days):
        date = today - timedelta(days=i)
        if date not in history:
            dates_to_backfill.append(date)
    
    # 3. 對每個缺失日期
    for date in dates_to_backfill:
        # 3.1 使用各幣種 DataFrame 中對應日期的數據
        # 3.2 計算該時間點的 RS(7)
        # 3.3 轉換為百分位排名
        # 3.4 保存到歷史檔案
        
        history[date] = percentiles
    
    # 4. 寫入檔案
    save_history(history)
```

這個方法的優點：
- 不需要額外的 API 請求
- 使用已載入的歷史 K 線數據
- 效率高，約 1-2 分鐘完成

---

## 📚 延伸閱讀

- [ZEABUR_DEPLOYMENT.md](./ZEABUR_DEPLOYMENT.md) - 完整部署指南
- [QUICKSTART.md](./QUICKSTART.md) - 快速啟動指南
- [README.md](./README.md) - 專案總覽

---

**總結：** 兩種方案都完全可行，選擇最適合您需求的即可！🚀
