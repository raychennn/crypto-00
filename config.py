"""
所有可調參數集中管理
唯一需要修改的檔案
"""
import os

# === 環境變數（從 .env 或 Zeabur 環境變數讀取） ===
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Telegram Bot 允許的用戶 ID（留空則允許所有人）
# 格式：["123456789", "987654321"]
TELEGRAM_ALLOWED_USERS = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",") if os.environ.get("TELEGRAM_ALLOWED_USERS") else []

# === 排程 ===
SCHEDULE_HOUR = 8
SCHEDULE_MINUTE = 0
TIMEZONE = "Asia/Taipei"
RUN_ON_STARTUP = False  # 啟動時是否立即執行一次

# === 數據 ===
DATA_DIR = "./data"
KLINE_HISTORY_DAYS = 60  # 拉取 K 線的歷史深度
API_REQUEST_DELAY = 0.15  # 每次 API 請求間隔（秒），避免 rate limit
API_MAX_RETRIES = 3  # API 失敗重試次數

# === 黑名單 ===
SYMBOL_BLACKLIST = [
    "BTCDOMUSDT",
    "ALLUSDT",
    "XAUUSDT",
    "XAGUSDT",
    "USDCUSDT",
    "TSLAUSDT",
    "INTCUSDT",
    "HOODUSDT",
    "MSTRUSDT",
    "AMZNUSDT",
    "CRCLUSDT",
    "COINUSDT",
    "PLTRUSDT",
    "XPTUSDT",
    "XPDUSDT",
    "PAXGUSDT",
]

# === 基礎過濾 ===
MIN_LISTING_DAYS = 30
MIN_MEDIAN_VOLUME = 100_000  # USD
MAX_MISSING_CANDLES = 2

# === 異常值 ===
ANOMALY_ATR_MULTIPLIER = 4

# === RS Rank ===
RS_SHORT_WINDOW = 7
RS_LONG_WINDOW = 21
RS_SHORT_THRESHOLD = 85  # 百分位門檻
RS_LONG_THRESHOLD = 70
DELTA_RS_LOOKBACK = 3

# ΔRS 歷史資料自動回推
AUTO_BACKFILL_RS_HISTORY = True  # 啟動時自動回推歷史排名
RS_HISTORY_BACKFILL_DAYS = 30    # 回推天數

# === T 值 ===
T_MA_PERIOD = 5
T_MAIN_WINDOW = 20
T_SHORT_WINDOW = 10
T_THRESHOLD = 50  # 百分位門檻
T2_MAX_RECURSION_DEPTH = 20

# === 加分維度 ===
VOL_SHORT = 5
VOL_LONG = 20
ATR_EXPAND_UPPER = 1.2
ATR_EXPAND_LOWER = 0.8
CORR_WINDOW = 7

# === 評分權重 ===
SCORE_WEIGHTS = {
    "rs7": 0.25,
    "t20": 0.20,
    "vol": 0.20,
    "drs": 0.20,
    "atr": 0.10,
    "corr": 0.05,
}

# === 市值分層 ===
USE_TIERS = False
TIER_LARGE = 50
TIER_MID = 200

# === 輸出 ===
TOP_N_DISPLAY = 30  # Telegram 推送顯示前 N 名

# === Telegram Bot 命令 ===
COMMAND_TIMEOUT = 300  # 命令執行超時時間（秒）
BACKTEST_MAX_DAYS = 0  # 回測可查詢天數上限（0 = 不限）
REVIEW_FUTURE_DAYS = 7  # 數據回顧的未來天數
