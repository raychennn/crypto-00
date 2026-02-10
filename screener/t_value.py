"""
T 值（趨勢品質量化）計算
"""
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import config
from utils import setup_logger

logger = setup_logger(__name__)


class TValueCalculator:
    """T 值計算器"""
    
    def calculate_ma(self, df: pd.DataFrame, period: int = config.T_MA_PERIOD) -> pd.Series:
        """
        計算移動平均線
        
        Args:
            df: K 線 DataFrame
            period: MA 週期
            
        Returns:
            MA 序列
        """
        return df['close'].rolling(window=period).mean()
    
    def calculate_sigma(self, df: pd.DataFrame, ma: pd.Series) -> np.ndarray:
        """
        計算位移狀態序列 σ(k)
        
        Args:
            df: K 線 DataFrame
            ma: MA 序列
            
        Returns:
            σ 序列（numpy array）
        """
        close = df['close'].values
        ma_values = ma.values
        is_anomaly = df['is_anomaly'].values if 'is_anomaly' in df.columns else np.zeros(len(df), dtype=bool)
        
        sigma = np.zeros(len(df))
        
        for k in range(1, len(df)):
            # 異常 K 線強制 σ = 0
            if is_anomaly[k]:
                sigma[k] = 0
                continue
            
            # 判定位移狀態
            close_prev = close[k-1]
            close_curr = close[k]
            ma_prev = ma_values[k-1]
            ma_curr = ma_values[k]
            
            # 跳過 MA 尚未計算完成的部分
            if pd.isna(ma_prev) or pd.isna(ma_curr):
                sigma[k] = 0
                continue
            
            # 從下方穿越到上方
            if close_prev < ma_prev and close_curr >= ma_curr:
                sigma[k] = 1
            
            # 從上方跌破到下方
            elif close_prev >= ma_prev and close_curr < ma_curr:
                sigma[k] = -1
            
            # 持續在上方
            elif close_prev >= ma_prev and close_curr >= ma_curr:
                if close_curr > close_prev:
                    sigma[k] = 1
                else:
                    sigma[k] = 0
            
            # 持續在下方
            elif close_prev < ma_prev and close_curr < ma_curr:
                if close_curr < close_prev:
                    sigma[k] = -1
                else:
                    sigma[k] = 0
        
        return sigma
    
    def calculate_cumulative_displacement(self, sigma: np.ndarray) -> np.ndarray:
        """
        計算累積位移路徑 S
        
        Args:
            sigma: 位移狀態序列
            
        Returns:
            累積位移序列 S
        """
        return np.cumsum(sigma)
    
    def calculate_t1(self, S: np.ndarray) -> float:
        """
        計算 T1（基於連續波段）
        
        Args:
            S: 累積位移序列
            
        Returns:
            T1 值
        """
        # 找出所有拐點（位移方向改變的點）
        # 忽略 σ = 0 的步驟，只看實際位移
        
        # 重建只包含實際位移的序列
        sigma = np.diff(np.concatenate([[0], S]))  # 還原 σ
        non_zero_indices = np.where(sigma != 0)[0]
        
        if len(non_zero_indices) == 0:
            return 0.0
        
        # 拐點序列（包含起點和終點）
        turning_points = [0]  # S(0) = 0
        
        if len(non_zero_indices) > 0:
            current_direction = np.sign(sigma[non_zero_indices[0]])
            
            for idx in non_zero_indices[1:]:
                direction = np.sign(sigma[idx])
                if direction != current_direction and direction != 0:
                    # 方向改變，前一個點為拐點
                    turning_points.append(idx - 1)
                    current_direction = direction
        
        # 加入終點
        turning_points.append(len(S) - 1)
        
        # 計算拐點之間的位移差
        S_prime = S[turning_points]
        d = np.abs(np.diff(S_prime))
        
        # T1 = Σ d(i)²
        t1 = np.sum(d ** 2)
        
        return t1
    
    def calculate_t2_recursive(
        self, 
        S: np.ndarray, 
        start: int, 
        end: int,
        depth: int = 0
    ) -> float:
        """
        遞迴計算 T2（基於絕對波動區間）
        
        Args:
            S: 累積位移序列
            start: 當前區間起始索引
            end: 當前區間結束索引
            depth: 遞迴深度
            
        Returns:
            當前區間的 T2 貢獻值
        """
        # 遞迴終止條件
        if end - start <= 1:
            return 0.0
        
        if depth >= config.T2_MAX_RECURSION_DEPTH:
            return 0.0
        
        # 找出當前區間的最大值和最小值
        segment = S[start:end+1]
        max_idx = np.argmax(segment) + start
        min_idx = np.argmin(segment) + start
        
        # 位移差
        delta = abs(S[max_idx] - S[min_idx])
        
        if delta == 0:
            return 0.0
        
        # 當前波段的貢獻
        contribution = delta ** 2
        
        # 確定切割順序（先出現的先切）
        if max_idx < min_idx:
            first_idx = max_idx
            second_idx = min_idx
        else:
            first_idx = min_idx
            second_idx = max_idx
        
        # 遞迴處理三個子區間
        left = self.calculate_t2_recursive(S, start, first_idx, depth + 1)
        middle = self.calculate_t2_recursive(S, first_idx, second_idx, depth + 1)
        right = self.calculate_t2_recursive(S, second_idx, end, depth + 1)
        
        return contribution + left + middle + right
    
    def calculate_t2(self, S: np.ndarray) -> float:
        """
        計算 T2
        
        Args:
            S: 累積位移序列
            
        Returns:
            T2 值
        """
        if len(S) <= 1:
            return 0.0
        
        return self.calculate_t2_recursive(S, 0, len(S) - 1)
    
    def calculate_t_value(self, df: pd.DataFrame, window: int) -> Tuple[float, float, int]:
        """
        計算指定窗口的 T 值
        
        Args:
            df: K 線 DataFrame
            window: 窗口大小
            
        Returns:
            (T 值, T_signed, S(N) 終點值)
        """
        if len(df) < window:
            return np.nan, np.nan, 0
        
        # 取最近 N 根 K 線
        recent_df = df.tail(window).copy().reset_index(drop=True)
        
        # 計算 MA
        ma = self.calculate_ma(recent_df)
        
        # 計算 σ
        sigma = self.calculate_sigma(recent_df, ma)
        
        # 計算累積位移 S
        S = self.calculate_cumulative_displacement(sigma)
        
        # S(N) 終點值
        S_N = S[-1]
        
        # 計算 T1 和 T2
        t1 = self.calculate_t1(S)
        t2 = self.calculate_t2(S)
        
        # T = max(T1, T2) / N^(3/2)
        N = window
        t_value = max(t1, t2) / (N ** 1.5)
        
        # T_signed = T × sign(S(N))
        t_signed = t_value * np.sign(S_N)
        
        return t_value, t_signed, S_N
    
    def filter_by_t_value(
        self, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict]]:
        """
        根據 T 值篩選幣種
        
        Args:
            data_dict: {symbol: DataFrame} 字典
            
        Returns:
            (通過篩選的 data_dict, T 值統計資料字典)
        """
        t_values = {}
        
        # 計算所有幣種的 T(20)
        for symbol, df in data_dict.items():
            try:
                t20, t20_signed, s_n = self.calculate_t_value(df, config.T_MAIN_WINDOW)
                
                if not pd.isna(t20):
                    t_values[symbol] = {
                        't20': t20,
                        't20_signed': t20_signed,
                        's_n': s_n
                    }
                    
            except Exception as e:
                logger.warning(f"{symbol}: 計算 T(20) 時發生錯誤: {e}")
                continue
        
        if not t_values:
            logger.warning("無幣種成功計算 T 值")
            return {}, {}
        
        # 只保留 S(N) > 0 的幣種（上升趨勢）
        uptrend_symbols = {
            symbol: stats 
            for symbol, stats in t_values.items() 
            if stats['s_n'] > 0
        }
        
        logger.info(f"T 值趨勢過濾：{len(t_values)} -> {len(uptrend_symbols)} 個幣種（S(N) > 0）")
        
        # 計算 T(20) 百分位
        t20_list = [stats['t20'] for stats in uptrend_symbols.values()]
        
        for symbol, stats in uptrend_symbols.items():
            t20 = stats['t20']
            percentile = (sum(v < t20 for v in t20_list) / len(t20_list)) * 100
            stats['t20_pct'] = percentile
        
        # 應用 T 值門檻篩選
        filtered = {}
        t_stats = {}
        
        for symbol, stats in uptrend_symbols.items():
            if stats['t20_pct'] >= config.T_THRESHOLD:
                filtered[symbol] = data_dict[symbol]
                t_stats[symbol] = stats
        
        logger.info(f"T 值門檻篩選：{len(uptrend_symbols)} -> {len(filtered)} 個幣種（T(20) ≥ {config.T_THRESHOLD}%）")
        
        return filtered, t_stats
    
    def calculate_t10_stable(
        self, 
        df: pd.DataFrame
    ) -> bool:
        """
        檢查 T(10) 是否穩定/上升
        
        Args:
            df: K 線 DataFrame（需包含足夠歷史數據）
            
        Returns:
            T(10) 今日 ≥ T(10) 3 天前
        """
        try:
            # 計算今日 T(10)
            t10_today, _, _ = self.calculate_t_value(df, config.T_SHORT_WINDOW)
            
            if pd.isna(t10_today):
                return False
            
            # 計算 3 天前的 T(10)
            if len(df) < config.T_SHORT_WINDOW + 3:
                return False
            
            df_3days_ago = df.iloc[:-3]
            t10_past, _, _ = self.calculate_t_value(df_3days_ago, config.T_SHORT_WINDOW)
            
            if pd.isna(t10_past):
                return False
            
            return t10_today >= t10_past
            
        except Exception as e:
            logger.warning(f"計算 T(10) 穩定性時發生錯誤: {e}")
            return False
