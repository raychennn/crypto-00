"""
基礎過濾、異常值處理、黑名單
"""
from datetime import datetime, timedelta
from typing import Dict

import numpy as np
import pandas as pd

import config
from utils import setup_logger

logger = setup_logger(__name__)


def check_listing_age(df: pd.DataFrame, symbol: str) -> bool:
    """
    檢查幣種上線天數是否符合要求
    
    Args:
        df: K 線 DataFrame
        symbol: 交易對名稱
        
    Returns:
        是否通過檢查
    """
    if len(df) < config.MIN_LISTING_DAYS:
        logger.debug(f"{symbol}: 上線天數 {len(df)} < {config.MIN_LISTING_DAYS}")
        return False
    
    return True


def check_liquidity(df: pd.DataFrame, symbol: str) -> bool:
    """
    檢查流動性：過去 7 天日成交量中位數
    
    Args:
        df: K 線 DataFrame（需包含 quote_volume 欄位）
        symbol: 交易對名稱
        
    Returns:
        是否通過檢查
    """
    if len(df) < 7:
        logger.debug(f"{symbol}: K 線數量不足 7 根")
        return False
    
    # 過去 7 天成交量中位數（USDT 計價）
    recent_volume = df.tail(7)['quote_volume']
    median_volume = recent_volume.median()
    
    if median_volume < config.MIN_MEDIAN_VOLUME:
        logger.debug(f"{symbol}: 7 日成交量中位數 {median_volume:.0f} < {config.MIN_MEDIAN_VOLUME}")
        return False
    
    return True


def apply_base_filters(
    data_dict: Dict[str, pd.DataFrame]
) -> Dict[str, pd.DataFrame]:
    """
    對所有幣種應用基礎過濾條件
    
    Args:
        data_dict: {symbol: DataFrame} 字典
        
    Returns:
        通過基礎過濾的 {symbol: DataFrame} 字典
    """
    filtered = {}
    
    for symbol, df in data_dict.items():
        try:
            # 檢查上線天數
            if not check_listing_age(df, symbol):
                continue
            
            # 檢查流動性
            if not check_liquidity(df, symbol):
                continue
            
            # 通過所有檢查
            filtered[symbol] = df
            
        except Exception as e:
            logger.warning(f"{symbol}: 基礎過濾時發生錯誤: {type(e).__name__} - {e}")
            continue
    
    logger.info(f"基礎過濾：{len(data_dict)} -> {len(filtered)} 個幣種")
    return filtered


def calculate_volume_percentile(
    data_dict: Dict[str, pd.DataFrame]
) -> Dict[str, float]:
    """
    計算各幣種的成交量百分位（用於市值分層）
    
    Args:
        data_dict: {symbol: DataFrame} 字典
        
    Returns:
        {symbol: 成交量排名百分位} 字典
    """
    volume_stats = {}
    
    for symbol, df in data_dict.items():
        try:
            # 計算過去 30 天日均成交量
            if len(df) >= 30:
                avg_volume = df.tail(30)['quote_volume'].mean()
                volume_stats[symbol] = avg_volume
            else:
                # 數據不足 30 天，用全部數據
                volume_stats[symbol] = df['quote_volume'].mean()
                
        except Exception as e:
            logger.warning(f"{symbol}: 計算成交量時發生錯誤: {e}")
            volume_stats[symbol] = 0
    
    # 轉換為百分位排名
    volumes = list(volume_stats.values())
    volume_percentiles = {}
    
    for symbol, vol in volume_stats.items():
        percentile = (sum(v < vol for v in volumes) / len(volumes)) * 100
        volume_percentiles[symbol] = percentile
    
    return volume_percentiles


def assign_tiers(
    data_dict: Dict[str, pd.DataFrame]
) -> Dict[str, str]:
    """
    根據成交量將幣種分配到不同層級
    
    Args:
        data_dict: {symbol: DataFrame} 字典
        
    Returns:
        {symbol: tier} 字典，tier 為 'large', 'mid', 'small'
    """
    if not config.USE_TIERS:
        # 不使用分層，全部歸為 'all'
        return {symbol: 'all' for symbol in data_dict.keys()}
    
    volume_percentiles = calculate_volume_percentile(data_dict)
    tiers = {}
    
    # 計算排名閾值
    symbols_sorted = sorted(
        volume_percentiles.items(), 
        key=lambda x: x[1], 
        reverse=True
    )
    
    total = len(symbols_sorted)
    large_threshold = config.TIER_LARGE
    mid_threshold = config.TIER_MID
    
    for rank, (symbol, _) in enumerate(symbols_sorted, start=1):
        if rank <= large_threshold:
            tiers[symbol] = 'large'
        elif rank <= mid_threshold:
            tiers[symbol] = 'mid'
        else:
            tiers[symbol] = 'small'
    
    # 統計各層級數量
    tier_counts = {}
    for tier in tiers.values():
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    logger.info(f"市值分層: {tier_counts}")
    
    return tiers
