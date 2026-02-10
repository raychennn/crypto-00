"""
加權評分模型與額外加分維度
"""
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

import config
from utils import setup_logger

logger = setup_logger(__name__)


class ScoringEngine:
    """評分引擎"""
    
    def __init__(self, btc_df: pd.DataFrame):
        """
        初始化評分引擎
        
        Args:
            btc_df: BTCUSDT 的 K 線 DataFrame
        """
        self.btc_df = btc_df
    
    def calculate_volume_ratio(self, df: pd.DataFrame) -> float:
        """
        計算成交量加速比率
        
        Args:
            df: K 線 DataFrame
            
        Returns:
            Vol_ratio = mean(quote_volume[-5:]) / mean(quote_volume[-20:])
        """
        if len(df) < config.VOL_LONG:
            return np.nan
        
        vol_short = df.tail(config.VOL_SHORT)['quote_volume'].mean()
        vol_long = df.tail(config.VOL_LONG)['quote_volume'].mean()
        
        if vol_long == 0:
            return np.nan
        
        return vol_short / vol_long
    
    def calculate_atr_ratio(self, df: pd.DataFrame) -> float:
        """
        計算 ATR 比率
        
        Args:
            df: K 線 DataFrame（需包含 high, low, close）
            
        Returns:
            ATR(5) / ATR(20)
        """
        if len(df) < 20:
            return np.nan
        
        # 計算 ATR(5) 和 ATR(20)
        atr_5 = self._calculate_atr(df, 5)
        atr_20 = self._calculate_atr(df, 20)
        
        if pd.isna(atr_5) or pd.isna(atr_20) or atr_20 == 0:
            return np.nan
        
        return atr_5 / atr_20
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> float:
        """
        計算指定週期的 ATR
        
        Args:
            df: K 線 DataFrame
            period: ATR 週期
            
        Returns:
            ATR 值
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1]
    
    def check_atr_expanding(self, df: pd.DataFrame) -> bool:
        """
        檢查波動率是否從壓縮展開
        
        Args:
            df: K 線 DataFrame
            
        Returns:
            是否滿足展開條件
        """
        if len(df) < 20:
            return False
        
        # 計算最近 5 根的 ATR 比率
        atr_ratios = []
        for i in range(5):
            df_subset = df.iloc[:-(i) if i > 0 else len(df)]
            ratio = self.calculate_atr_ratio(df_subset)
            if not pd.isna(ratio):
                atr_ratios.append(ratio)
        
        if len(atr_ratios) < 5:
            return False
        
        current_ratio = atr_ratios[0]
        past_ratios = atr_ratios[1:4]  # 倒數 2-4 根
        
        # 當前展開 + 過去壓縮
        expanding = (
            current_ratio > config.ATR_EXPAND_UPPER and
            min(past_ratios) < config.ATR_EXPAND_LOWER
        )
        
        return expanding
    
    def calculate_btc_correlation(self, df: pd.DataFrame) -> float:
        """
        計算與 BTC 的相關性
        
        Args:
            df: 幣種 K 線 DataFrame
            
        Returns:
            相關係數（-1 到 1）
        """
        if len(df) < config.CORR_WINDOW or len(self.btc_df) < config.CORR_WINDOW:
            return np.nan
        
        # 取最近 N 天的日報酬率
        coin_returns = df.tail(config.CORR_WINDOW)['return'].dropna()
        btc_returns = self.btc_df.tail(config.CORR_WINDOW)['return'].dropna()
        
        # 確保長度一致
        min_len = min(len(coin_returns), len(btc_returns))
        if min_len < 3:  # 至少需要 3 個點才能計算相關性
            return np.nan
        
        coin_returns = coin_returns.tail(min_len).values
        btc_returns = btc_returns.tail(min_len).values
        
        try:
            corr, _ = pearsonr(coin_returns, btc_returns)
            return corr
        except Exception as e:
            logger.warning(f"計算 BTC 相關性時發生錯誤: {e}")
            return np.nan
    
    def calculate_all_metrics(
        self, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, Dict]:
        """
        計算所有加分維度的指標
        
        Args:
            data_dict: {symbol: DataFrame} 字典
            
        Returns:
            {symbol: 指標字典} 字典
        """
        metrics = {}
        
        for symbol, df in data_dict.items():
            try:
                metrics[symbol] = {
                    'vol_ratio': self.calculate_volume_ratio(df),
                    'atr_ratio': self.calculate_atr_ratio(df),
                    'atr_expanding': self.check_atr_expanding(df),
                    'corr_btc': self.calculate_btc_correlation(df)
                }
            except Exception as e:
                logger.warning(f"{symbol}: 計算加分指標時發生錯誤: {e}")
                metrics[symbol] = {
                    'vol_ratio': np.nan,
                    'atr_ratio': np.nan,
                    'atr_expanding': False,
                    'corr_btc': np.nan
                }
        
        return metrics
    
    def calculate_percentile_ranks(
        self, 
        metrics: Dict[str, Dict]
    ) -> Dict[str, Dict]:
        """
        將所有指標轉換為百分位排名
        
        Args:
            metrics: {symbol: 指標字典} 字典
            
        Returns:
            {symbol: 百分位排名字典} 字典
        """
        # 收集各維度的值
        vol_ratios = []
        atr_ratios = []
        corr_btc_values = []
        
        for symbol, m in metrics.items():
            if not pd.isna(m['vol_ratio']):
                vol_ratios.append((symbol, m['vol_ratio']))
            if not pd.isna(m['atr_ratio']):
                atr_ratios.append((symbol, m['atr_ratio']))
            if not pd.isna(m['corr_btc']):
                corr_btc_values.append((symbol, m['corr_btc']))
        
        # 計算百分位
        percentile_ranks = {}
        
        for symbol in metrics.keys():
            percentile_ranks[symbol] = {}
        
        # Vol ratio 百分位
        if vol_ratios:
            all_vals = [v for _, v in vol_ratios]
            for symbol, val in vol_ratios:
                pct = (sum(v < val for v in all_vals) / len(all_vals)) * 100
                percentile_ranks[symbol]['score_vol'] = pct
        
        # ATR ratio 百分位
        if atr_ratios:
            all_vals = [v for _, v in atr_ratios]
            for symbol, val in atr_ratios:
                pct = (sum(v < val for v in all_vals) / len(all_vals)) * 100
                percentile_ranks[symbol]['score_atr'] = pct
        
        # BTC 低相關性百分位（1 - corr_btc）
        if corr_btc_values:
            all_vals = [1 - v for _, v in corr_btc_values]  # 轉換為低相關性指標
            for symbol, corr in corr_btc_values:
                low_corr = 1 - corr
                pct = (sum(v < low_corr for v in all_vals) / len(all_vals)) * 100
                percentile_ranks[symbol]['score_corr'] = pct
        
        # 填充缺失值為 50（中位數）
        for symbol in percentile_ranks.keys():
            if 'score_vol' not in percentile_ranks[symbol]:
                percentile_ranks[symbol]['score_vol'] = 50.0
            if 'score_atr' not in percentile_ranks[symbol]:
                percentile_ranks[symbol]['score_atr'] = 50.0
            if 'score_corr' not in percentile_ranks[symbol]:
                percentile_ranks[symbol]['score_corr'] = 50.0
        
        return percentile_ranks
    
    def calculate_final_scores(
        self, 
        rs_stats: Dict[str, Dict],
        t_stats: Dict[str, Dict],
        delta_rs: Dict[str, float],
        metrics: Dict[str, Dict]
    ) -> pd.DataFrame:
        """
        計算最終加權評分
        
        Args:
            rs_stats: RS 統計資料
            t_stats: T 值統計資料
            delta_rs: ΔRS 資料
            metrics: 加分指標
            
        Returns:
            包含所有評分的 DataFrame
        """
        # 找出所有候選幣種（通過 RS 和 T 篩選的交集）
        symbols = set(rs_stats.keys()) & set(t_stats.keys())
        
        if not symbols:
            logger.warning("無幣種通過所有篩選")
            return pd.DataFrame()
        
        # 計算額外指標的百分位排名
        percentile_ranks = self.calculate_percentile_ranks(metrics)
        
        # 計算 ΔRS 的百分位
        delta_rs_valid = {s: v for s, v in delta_rs.items() if v is not None and s in symbols}
        
        if delta_rs_valid:
            all_drs = list(delta_rs_valid.values())
            drs_percentiles = {}
            for symbol, drs in delta_rs_valid.items():
                pct = (sum(v < drs for v in all_drs) / len(all_drs)) * 100
                drs_percentiles[symbol] = pct
        else:
            drs_percentiles = {}
        
        # 組裝評分數據
        scores_data = []
        
        for symbol in symbols:
            # 基礎分數
            score_rs7 = rs_stats[symbol]['rs7_pct']
            score_t20 = t_stats[symbol]['t20_pct']
            
            # 額外維度分數
            score_vol = percentile_ranks.get(symbol, {}).get('score_vol', 50.0)
            score_atr = percentile_ranks.get(symbol, {}).get('score_atr', 50.0)
            score_corr = percentile_ranks.get(symbol, {}).get('score_corr', 50.0)
            score_drs = drs_percentiles.get(symbol, 50.0)  # ΔRS 缺失時用 50
            
            # 加權計算最終評分
            final_score = (
                config.SCORE_WEIGHTS['rs7'] * score_rs7 +
                config.SCORE_WEIGHTS['t20'] * score_t20 +
                config.SCORE_WEIGHTS['vol'] * score_vol +
                config.SCORE_WEIGHTS['drs'] * score_drs +
                config.SCORE_WEIGHTS['atr'] * score_atr +
                config.SCORE_WEIGHTS['corr'] * score_corr
            )
            
            scores_data.append({
                'symbol': symbol,
                'rs7_pct': rs_stats[symbol]['rs7_pct'],
                'rs21_pct': rs_stats[symbol]['rs21_pct'],
                'delta_rs': delta_rs.get(symbol),
                't20': t_stats[symbol]['t20'],
                't20_pct': t_stats[symbol]['t20_pct'],
                'vol_ratio': metrics.get(symbol, {}).get('vol_ratio'),
                'atr_ratio': metrics.get(symbol, {}).get('atr_ratio'),
                'atr_expanding': metrics.get(symbol, {}).get('atr_expanding', False),
                'corr_btc': metrics.get(symbol, {}).get('corr_btc'),
                'score_rs7': score_rs7,
                'score_t20': score_t20,
                'score_vol': score_vol,
                'score_drs': score_drs,
                'score_atr': score_atr,
                'score_corr': score_corr,
                'final_score': final_score
            })
        
        # 轉換為 DataFrame 並排序
        df_scores = pd.DataFrame(scores_data)
        df_scores = df_scores.sort_values('final_score', ascending=False).reset_index(drop=True)
        
        logger.info(f"計算了 {len(df_scores)} 個幣種的最終評分")
        
        return df_scores
