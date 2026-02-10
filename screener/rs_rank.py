"""
RS Rank（相對強度排名）計算
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

import config
from utils import setup_logger

logger = setup_logger(__name__)


class RSRankCalculator:
    """RS Rank 計算器"""
    
    def __init__(self, btc_df: pd.DataFrame):
        """
        初始化 RS Rank 計算器
        
        Args:
            btc_df: BTCUSDT 的 K 線 DataFrame
        """
        self.btc_df = btc_df
        self.history_file = Path(config.DATA_DIR) / "rs_rank_history.json"
        
        # 確保目錄存在
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
    
    def calculate_return(self, df: pd.DataFrame, window: int) -> float:
        """
        計算 N 天累積報酬率
        
        Args:
            df: K 線 DataFrame
            window: 窗口大小
            
        Returns:
            累積報酬率（百分比形式）
        """
        if len(df) < window + 1:
            return np.nan
        
        current_close = df.iloc[-1]['close']
        past_close = df.iloc[-(window + 1)]['close']
        
        if past_close == 0 or pd.isna(past_close):
            return np.nan
        
        return (current_close / past_close - 1) * 100
    
    def calculate_rs_diff(
        self, 
        coin_df: pd.DataFrame, 
        window: int
    ) -> float:
        """
        計算差值形式的相對強度
        
        Args:
            coin_df: 幣種 K 線 DataFrame
            window: 窗口大小
            
        Returns:
            RS_diff = 幣種報酬率 - BTC 報酬率
        """
        coin_return = self.calculate_return(coin_df, window)
        btc_return = self.calculate_return(self.btc_df, window)
        
        if pd.isna(coin_return) or pd.isna(btc_return):
            return np.nan
        
        return coin_return - btc_return
    
    def calculate_rs_percentiles(
        self, 
        data_dict: Dict[str, pd.DataFrame],
        window: int
    ) -> Dict[str, float]:
        """
        計算所有幣種的 RS 百分位排名
        
        Args:
            data_dict: {symbol: DataFrame} 字典
            window: RS 窗口大小
            
        Returns:
            {symbol: RS 百分位} 字典（0-100）
        """
        rs_values = {}
        
        # 計算每個幣種的 RS_diff
        for symbol, df in data_dict.items():
            try:
                rs_diff = self.calculate_rs_diff(df, window)
                if not pd.isna(rs_diff):
                    rs_values[symbol] = rs_diff
            except Exception as e:
                logger.warning(f"{symbol}: 計算 RS({window}) 時發生錯誤: {e}")
                continue
        
        if not rs_values:
            logger.warning(f"無幣種成功計算 RS({window})")
            return {}
        
        # 轉換為百分位排名
        all_rs = list(rs_values.values())
        percentiles = {}
        
        for symbol, rs in rs_values.items():
            percentile = (sum(v < rs for v in all_rs) / len(all_rs)) * 100
            percentiles[symbol] = percentile
        
        logger.info(f"RS({window}): 計算了 {len(percentiles)} 個幣種的百分位")
        
        return percentiles
    
    def filter_by_rs_rank(
        self, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict[str, float]]]:
        """
        根據 RS Rank 篩選幣種
        
        Args:
            data_dict: {symbol: DataFrame} 字典
            
        Returns:
            (通過篩選的 data_dict, RS 統計資料字典)
        """
        # 計算兩個窗口的 RS 百分位
        rs7_pct = self.calculate_rs_percentiles(data_dict, config.RS_SHORT_WINDOW)
        rs21_pct = self.calculate_rs_percentiles(data_dict, config.RS_LONG_WINDOW)
        
        filtered = {}
        rs_stats = {}
        
        for symbol in data_dict.keys():
            try:
                # 檢查是否有 RS 數據
                if symbol not in rs7_pct or symbol not in rs21_pct:
                    continue
                
                rs7 = rs7_pct[symbol]
                rs21 = rs21_pct[symbol]
                
                # 應用篩選條件
                if (rs7 >= config.RS_SHORT_THRESHOLD and
                    rs21 >= config.RS_LONG_THRESHOLD and
                    rs7 > rs21):
                    
                    filtered[symbol] = data_dict[symbol]
                    rs_stats[symbol] = {
                        'rs7_pct': rs7,
                        'rs21_pct': rs21
                    }
                
            except Exception as e:
                logger.warning(f"{symbol}: RS 篩選時發生錯誤: {e}")
                continue
        
        logger.info(f"RS 篩選：{len(data_dict)} -> {len(filtered)} 個幣種")
        
        return filtered, rs_stats
    
    def calculate_delta_rs(
        self, 
        current_rs7_pct: Dict[str, float]
    ) -> Dict[str, Optional[float]]:
        """
        計算 ΔRS（RS 排名變化速度）
        
        Args:
            current_rs7_pct: 當前的 RS(7) 百分位字典
            
        Returns:
            {symbol: ΔRS 值} 字典，若無歷史數據則為 None
        """
        delta_rs = {}
        
        # 讀取歷史排名
        history = self.load_history()
        
        # 計算需要比較的日期
        lookback_date = (
            datetime.utcnow().date() - 
            pd.Timedelta(days=config.DELTA_RS_LOOKBACK)
        ).isoformat()
        
        if lookback_date in history:
            past_rs7_pct = history[lookback_date]
            
            for symbol, current_pct in current_rs7_pct.items():
                if symbol in past_rs7_pct:
                    delta_rs[symbol] = current_pct - past_rs7_pct[symbol]
                else:
                    delta_rs[symbol] = None  # 過去無此幣種
        else:
            logger.info(f"無 {lookback_date} 的歷史排名數據，ΔRS 將為 None")
            delta_rs = {symbol: None for symbol in current_rs7_pct.keys()}
        
        # 保存當前排名到歷史
        self.save_history(current_rs7_pct)
        
        return delta_rs
    
    def load_history(self) -> Dict[str, Dict[str, float]]:
        """
        讀取歷史 RS 排名數據
        
        Returns:
            {date: {symbol: rs7_pct}} 字典
        """
        if not self.history_file.exists():
            return {}
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"讀取 RS 歷史數據失敗: {e}")
            return {}
    
    def save_history(self, current_rs7_pct: Dict[str, float]):
        """
        保存當前 RS 排名到歷史檔案
        
        Args:
            current_rs7_pct: 當前的 RS(7) 百分位字典
        """
        try:
            history = self.load_history()
            
            # 加入當前日期的數據
            today = datetime.utcnow().date().isoformat()
            history[today] = current_rs7_pct
            
            # 只保留最近 30 天的歷史（避免檔案過大）
            dates_sorted = sorted(history.keys(), reverse=True)
            if len(dates_sorted) > 30:
                for old_date in dates_sorted[30:]:
                    del history[old_date]
            
            # 寫入檔案
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
            
            logger.info(f"已保存 RS 排名歷史到 {self.history_file}")
            
        except Exception as e:
            logger.error(f"保存 RS 歷史數據失敗: {e}")
    
    def backfill_history(self, data_dict: Dict[str, pd.DataFrame]):
        """
        自動回推歷史 RS 排名資料
        
        Args:
            data_dict: {symbol: DataFrame} 字典（需包含足夠的歷史數據）
        """
        logger.info("開始回推 RS 歷史排名資料...")
        
        try:
            history = self.load_history()
            
            # 計算需要回推的日期範圍
            today = datetime.utcnow().date()
            backfill_days = config.RS_HISTORY_BACKFILL_DAYS
            
            # 找出歷史資料中已有的最早日期
            existing_dates = set(history.keys()) if history else set()
            
            dates_to_backfill = []
            for i in range(backfill_days):
                date = (today - timedelta(days=i)).isoformat()
                if date not in existing_dates:
                    dates_to_backfill.append(date)
            
            if not dates_to_backfill:
                logger.info("RS 歷史資料已充足，無需回推")
                return
            
            logger.info(f"需要回推 {len(dates_to_backfill)} 天的 RS 排名")
            
            # 對每個需要回推的日期計算 RS(7) 百分位
            dates_to_backfill.sort()  # 從舊到新
            
            for date_str in dates_to_backfill:
                try:
                    # 計算該日期的 RS(7) 百分位
                    # 這裡使用各幣種 DataFrame 中對應日期的數據
                    target_date = datetime.fromisoformat(date_str)
                    
                    # 為每個幣種找到該日期對應的索引
                    rs7_pct_at_date = {}
                    
                    for symbol, df in data_dict.items():
                        try:
                            # 找到該日期或之前最近的數據點
                            df_at_date = df[df['open_time'].dt.date <= target_date.date()]
                            
                            if len(df_at_date) < config.RS_SHORT_WINDOW + 1:
                                continue
                            
                            # 計算該時間點的 RS(7)
                            rs_diff = self.calculate_rs_diff_at_index(
                                df_at_date, 
                                len(df_at_date) - 1,
                                config.RS_SHORT_WINDOW
                            )
                            
                            if not pd.isna(rs_diff):
                                rs7_pct_at_date[symbol] = rs_diff
                                
                        except Exception as e:
                            continue
                    
                    if rs7_pct_at_date:
                        # 轉換為百分位
                        all_rs = list(rs7_pct_at_date.values())
                        percentiles = {}
                        for symbol, rs in rs7_pct_at_date.items():
                            pct = (sum(v < rs for v in all_rs) / len(all_rs)) * 100
                            percentiles[symbol] = pct
                        
                        # 保存到歷史
                        history[date_str] = percentiles
                        
                except Exception as e:
                    logger.warning(f"回推 {date_str} 的 RS 排名失敗: {e}")
                    continue
            
            # 保存回推結果
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
            
            logger.info(f"RS 歷史排名回推完成，共回推 {len(dates_to_backfill)} 天")
            
        except Exception as e:
            logger.error(f"回推 RS 歷史資料失敗: {e}")
    
    def calculate_rs_diff_at_index(
        self, 
        coin_df: pd.DataFrame, 
        index: int,
        window: int
    ) -> float:
        """
        計算特定索引位置的 RS_diff
        
        Args:
            coin_df: 幣種 K 線 DataFrame
            index: 目標索引
            window: 窗口大小
            
        Returns:
            RS_diff 值
        """
        if index < window:
            return np.nan
        
        # 計算幣種報酬率
        current_close = coin_df.iloc[index]['close']
        past_close = coin_df.iloc[index - window]['close']
        
        if past_close == 0 or pd.isna(past_close):
            return np.nan
        
        coin_return = (current_close / past_close - 1) * 100
        
        # 計算 BTC 報酬率
        if index >= len(self.btc_df) or index - window < 0:
            return np.nan
        
        btc_current = self.btc_df.iloc[min(index, len(self.btc_df) - 1)]['close']
        btc_past = self.btc_df.iloc[max(0, index - window)]['close']
        
        if btc_past == 0 or pd.isna(btc_past):
            return np.nan
        
        btc_return = (btc_current / btc_past - 1) * 100
        
        return coin_return - btc_return

