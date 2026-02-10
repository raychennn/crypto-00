"""
幣安 API 數據拉取與前處理
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config
from utils import setup_logger

logger = setup_logger(__name__)


class BinanceDataFetcher:
    """幣安數據拉取器"""
    
    def __init__(self):
        """初始化幣安客戶端"""
        self.client = Client(
            api_key=config.BINANCE_API_KEY,
            api_secret=config.BINANCE_API_SECRET
        )
    
    def get_all_usdt_perpetual_symbols(self) -> List[str]:
        """
        獲取所有 USDT 保證金永續合約交易對
        
        Returns:
            交易對列表
        """
        try:
            exchange_info = self.client.futures_exchange_info()
            symbols = []
            
            for symbol_info in exchange_info['symbols']:
                # 只保留 USDT 保證金永續合約
                if (symbol_info['quoteAsset'] == 'USDT' and 
                    symbol_info['contractType'] == 'PERPETUAL' and
                    symbol_info['status'] == 'TRADING'):
                    
                    symbol = symbol_info['symbol']
                    
                    # 排除黑名單
                    if symbol not in config.SYMBOL_BLACKLIST:
                        symbols.append(symbol)
            
            logger.info(f"找到 {len(symbols)} 個 USDT 永續合約交易對（已排除黑名單）")
            return symbols
            
        except BinanceAPIException as e:
            logger.error(f"獲取交易對列表失敗: {e}")
            raise
    
    def fetch_klines(
        self, 
        symbol: str, 
        days: int = config.KLINE_HISTORY_DAYS,
        retries: int = config.API_MAX_RETRIES
    ) -> Optional[pd.DataFrame]:
        """
        拉取指定交易對的日線數據
        
        Args:
            symbol: 交易對名稱
            days: 拉取天數
            retries: 重試次數
            
        Returns:
            DataFrame 包含 OHLCV 數據，若失敗則返回 None
        """
        for attempt in range(retries):
            try:
                # 計算起始時間
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=days)
                
                # 拉取 K 線數據
                klines = self.client.futures_klines(
                    symbol=symbol,
                    interval=Client.KLINE_INTERVAL_1DAY,
                    startTime=int(start_time.timestamp() * 1000),
                    endTime=int(end_time.timestamp() * 1000),
                    limit=1000
                )
                
                if not klines:
                    logger.warning(f"{symbol}: 無 K 線數據")
                    return None
                
                # 轉換為 DataFrame
                df = pd.DataFrame(klines, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                
                # 轉換數據類型
                df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # 只保留需要的欄位
                df = df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume']]
                df = df.sort_values('open_time').reset_index(drop=True)
                
                # 延遲避免 rate limit
                time.sleep(config.API_REQUEST_DELAY)
                
                return df
                
            except BinanceAPIException as e:
                if e.code == -1121:  # Invalid symbol
                    logger.warning(f"{symbol}: 無效的交易對")
                    return None
                elif e.code == 429:  # Rate limit
                    wait_time = 2 ** attempt  # 指數退避
                    logger.warning(f"{symbol}: 遇到 rate limit，等待 {wait_time}s 後重試（{attempt+1}/{retries}）")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"{symbol}: API 錯誤 {e.code} - {e.message}")
                    if attempt < retries - 1:
                        time.sleep(1)
                    else:
                        return None
                        
            except ConnectionError as e:
                wait_time = 2 ** attempt
                logger.warning(f"{symbol}: 網路錯誤，等待 {wait_time}s 後重試（{attempt+1}/{retries}）: {e}")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"{symbol}: 未預期錯誤: {type(e).__name__} - {e}")
                return None
        
        logger.error(f"{symbol}: 達到最大重試次數，放棄拉取")
        return None
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        計算平均真實波幅（ATR）
        
        Args:
            df: OHLC DataFrame
            period: ATR 週期
            
        Returns:
            ATR 序列
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = TR 的移動平均
        atr = tr.rolling(window=period).mean()
        
        return atr


def preprocess_data(df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, bool]:
    """
    對原始 K 線數據進行前處理
    
    Args:
        df: 原始 K 線 DataFrame
        symbol: 交易對名稱
        
    Returns:
        (處理後的 DataFrame, 是否通過數據完整性檢查)
    """
    # 檢查數據完整性：最近 30 根 K 線缺失數不超過 2 根
    if len(df) < 30:
        logger.warning(f"{symbol}: K 線數量不足 30 根")
        return df, False
    
    recent_30 = df.tail(30)
    missing_count = recent_30[['open', 'high', 'low', 'close']].isna().any(axis=1).sum()
    
    if missing_count > config.MAX_MISSING_CANDLES:
        logger.warning(f"{symbol}: 最近 30 根 K 線缺失 {missing_count} 根，超過上限 {config.MAX_MISSING_CANDLES}")
        return df, False
    
    # 填充缺失值（前向填充）
    df = df.ffill()
    
    # 計算報酬率
    df['return'] = df['close'].pct_change()
    
    # 計算 ATR(14) 用於異常值檢測
    fetcher = BinanceDataFetcher()
    df['atr_14'] = fetcher.calculate_atr(df, period=14)
    
    # 標記異常值
    df['is_anomaly'] = False
    for i in range(14, len(df)):  # ATR 需要至少 14 根 K 線
        if pd.notna(df.loc[i, 'atr_14']) and df.loc[i, 'atr_14'] > 0:
            return_abs = abs(df.loc[i, 'return'])
            threshold = config.ANOMALY_ATR_MULTIPLIER * df.loc[i, 'atr_14']
            
            if return_abs > threshold:
                df.loc[i, 'is_anomaly'] = True
    
    anomaly_count = df['is_anomaly'].sum()
    if anomaly_count > 0:
        logger.info(f"{symbol}: 標記 {anomaly_count} 根異常 K 線")
    
    return df, True
