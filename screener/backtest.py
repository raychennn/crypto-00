"""
回測功能：查詢指定日期的篩選結果
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import pandas as pd
from binance.client import Client

import config
from screener.data import BinanceDataFetcher, preprocess_data
from screener.filters import apply_base_filters, assign_tiers
from screener.rs_rank import RSRankCalculator
from screener.t_value import TValueCalculator
from screener.scoring import ScoringEngine
from utils import setup_logger

logger = setup_logger(__name__)


class BacktestEngine:
    """回測引擎：查詢歷史特定日期的篩選結果"""
    
    def __init__(self):
        """初始化回測引擎"""
        self.fetcher = BinanceDataFetcher()
    
    def fetch_historical_klines(
        self, 
        symbol: str, 
        end_date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        拉取截止到指定日期的 K 線數據（不偷看未來）
        
        Args:
            symbol: 交易對名稱
            end_date: 截止日期（GMT+8 00:00 對應的 UTC 時間）
            
        Returns:
            K 線 DataFrame
        """
        try:
            # 確保 end_date 是 UTC 時間的當日 00:00
            # GMT+8 00:00 = UTC 前一日 16:00
            end_time_utc = end_date - timedelta(hours=8)
            end_time_utc = end_time_utc.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # 起始時間：往前推 KLINE_HISTORY_DAYS 天
            start_time_utc = end_time_utc - timedelta(days=config.KLINE_HISTORY_DAYS)
            
            # 拉取 K 線
            klines = self.fetcher.client.futures_klines(
                symbol=symbol,
                interval=Client.KLINE_INTERVAL_1DAY,
                startTime=int(start_time_utc.timestamp() * 1000),
                endTime=int(end_time_utc.timestamp() * 1000),
                limit=1000
            )
            
            if not klines:
                return None
            
            # 轉換為 DataFrame
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume']]
            df = df.sort_values('open_time').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.warning(f"{symbol}: 拉取歷史 K 線失敗: {type(e).__name__} - {e}")
            return None
    
    def run_backtest(
        self, 
        target_date: datetime,
        single_symbol: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Dict, Optional[Dict]]:
        """
        執行回測：在指定日期做篩選
        
        Args:
            target_date: 目標日期（GMT+8 的日期）
            single_symbol: 單一幣種查詢（若指定，則返回該幣種的詳細檢查結果）
            
        Returns:
            (評分結果 DataFrame, 統計資訊, 單幣種檢查詳情)
        """
        logger.info(f"開始回測：目標日期 {target_date.strftime('%Y-%m-%d')}")
        
        stats = {'target_date': target_date.strftime('%Y-%m-%d')}
        single_symbol_check = None
        
        try:
            # 1. 獲取所有交易對
            all_symbols = self.fetcher.get_all_usdt_perpetual_symbols()
            stats['total_symbols'] = len(all_symbols)
            
            # 若指定單一幣種查詢，確保該幣種在列表中
            if single_symbol:
                if single_symbol not in all_symbols:
                    single_symbol_check = {
                        'symbol': single_symbol,
                        'status': 'not_trading',
                        'message': f'{single_symbol} 在 {target_date.strftime("%Y-%m-%d")} 不存在或未交易'
                    }
                    return pd.DataFrame(), stats, single_symbol_check
                
                # 初始化檢查結果
                single_symbol_check = {
                    'symbol': single_symbol,
                    'status': 'checking',
                    'checks': {}
                }
            
            # 2. 拉取 BTC 歷史數據
            logger.info("拉取 BTCUSDT 歷史數據...")
            btc_df = self.fetch_historical_klines('BTCUSDT', target_date)
            
            if btc_df is None or len(btc_df) < config.MIN_LISTING_DAYS:
                raise ValueError(
                    f"無法獲取足夠的 BTCUSDT 歷史數據"
                    f"（取得 {len(btc_df) if btc_df is not None else 0} 根，"
                    f"需要至少 {config.MIN_LISTING_DAYS} 根）"
                )
            
            btc_df, _ = preprocess_data(btc_df, 'BTCUSDT')
            
            # 3. 拉取所有幣種歷史數據
            logger.info(f"拉取 {len(all_symbols)} 個幣種的歷史 K 線...")
            data_dict = {}
            
            # 若是單幣種查詢，優先處理該幣種
            symbols_to_fetch = [single_symbol] if single_symbol else all_symbols
            if single_symbol:
                # 單幣種查詢時，仍需拉取其他幣種以計算百分位
                symbols_to_fetch = all_symbols
            
            for i, symbol in enumerate(symbols_to_fetch, 1):
                if i % 50 == 0 and not single_symbol:
                    logger.info(f"進度: {i}/{len(symbols_to_fetch)}")
                
                try:
                    df = self.fetch_historical_klines(symbol, target_date)
                    
                    if df is not None and len(df) >= config.MIN_LISTING_DAYS:
                        df_processed, data_ok = preprocess_data(df, symbol)
                        
                        if data_ok:
                            data_dict[symbol] = df_processed
                            
                except Exception as e:
                    logger.warning(f"{symbol}: 處理歷史數據時發生錯誤: {e}")
                    continue
            
            stats['loaded_symbols'] = len(data_dict)
            
            # 單幣種檢查：是否載入成功
            if single_symbol and single_symbol_check:
                if single_symbol in data_dict:
                    single_symbol_check['checks']['data_loaded'] = True
                else:
                    single_symbol_check['checks']['data_loaded'] = False
                    single_symbol_check['status'] = 'failed'
                    single_symbol_check['failed_at'] = 'data_loading'
                    single_symbol_check['message'] = '數據載入失敗或上線天數不足'
                    return pd.DataFrame(), stats, single_symbol_check
            
            # 4. 基礎過濾
            filtered_data = apply_base_filters(data_dict)
            stats['base_filtered'] = len(filtered_data)
            
            # 單幣種檢查：基礎過濾
            if single_symbol and single_symbol_check:
                if single_symbol in filtered_data:
                    single_symbol_check['checks']['base_filter'] = True
                else:
                    single_symbol_check['checks']['base_filter'] = False
                    single_symbol_check['status'] = 'failed'
                    single_symbol_check['failed_at'] = 'base_filter'
                    
                    # 詳細說明未通過原因
                    reasons = []
                    df = data_dict[single_symbol]
                    
                    if len(df) < config.MIN_LISTING_DAYS:
                        reasons.append(f'上線天數不足（{len(df)} < {config.MIN_LISTING_DAYS}）')
                    
                    if len(df) >= 7:
                        median_vol = df.tail(7)['quote_volume'].median()
                        if median_vol < config.MIN_MEDIAN_VOLUME:
                            reasons.append(f'成交量不足（7日中位數 {median_vol:.0f} < {config.MIN_MEDIAN_VOLUME}）')
                    
                    single_symbol_check['message'] = '未通過基礎過濾：' + '、'.join(reasons)
                    return pd.DataFrame(), stats, single_symbol_check
            
            if not filtered_data:
                return pd.DataFrame(), stats, single_symbol_check
            
            # 5. 市值分層
            tiers = assign_tiers(filtered_data)
            
            # 6. RS Rank 篩選
            rs_calculator = RSRankCalculator(btc_df)
            rs_filtered, rs_stats = rs_calculator.filter_by_rs_rank(filtered_data)
            stats['rs_filtered'] = len(rs_filtered)
            
            # 單幣種檢查：RS 篩選
            if single_symbol and single_symbol_check:
                if single_symbol in rs_stats:
                    single_symbol_check['checks']['rs_filter'] = True
                    single_symbol_check['rs_stats'] = rs_stats[single_symbol]
                else:
                    single_symbol_check['checks']['rs_filter'] = False
                    single_symbol_check['status'] = 'failed'
                    single_symbol_check['failed_at'] = 'rs_filter'
                    
                    # 計算該幣種的 RS 百分位（即使未通過篩選）
                    rs7_all = rs_calculator.calculate_rs_percentiles(filtered_data, config.RS_SHORT_WINDOW)
                    rs21_all = rs_calculator.calculate_rs_percentiles(filtered_data, config.RS_LONG_WINDOW)
                    
                    rs7_pct = rs7_all.get(single_symbol, 0)
                    rs21_pct = rs21_all.get(single_symbol, 0)
                    
                    reasons = []
                    if rs7_pct < config.RS_SHORT_THRESHOLD:
                        reasons.append(f'RS(7) 百分位 {rs7_pct:.1f}% < {config.RS_SHORT_THRESHOLD}%')
                    if rs21_pct < config.RS_LONG_THRESHOLD:
                        reasons.append(f'RS(21) 百分位 {rs21_pct:.1f}% < {config.RS_LONG_THRESHOLD}%')
                    if rs7_pct <= rs21_pct:
                        reasons.append(f'RS(7) {rs7_pct:.1f}% ≤ RS(21) {rs21_pct:.1f}%（動量未加速）')
                    
                    single_symbol_check['message'] = '未通過 RS 篩選：' + '、'.join(reasons)
                    single_symbol_check['rs_stats'] = {'rs7_pct': rs7_pct, 'rs21_pct': rs21_pct}
                    return pd.DataFrame(), stats, single_symbol_check
            
            if not rs_filtered:
                return pd.DataFrame(), stats, single_symbol_check
            
            # 7. ΔRS（歷史回測不計算 ΔRS，設為 None）
            delta_rs = {s: None for s in rs_stats.keys()}
            
            # 8. T 值篩選
            t_calculator = TValueCalculator()
            t_filtered, t_stats = t_calculator.filter_by_t_value(rs_filtered)
            stats['t_filtered'] = len(t_filtered)
            
            # 單幣種檢查：T 值篩選
            if single_symbol and single_symbol_check:
                if single_symbol in t_stats:
                    single_symbol_check['checks']['t_filter'] = True
                    single_symbol_check['t_stats'] = {
                        't20': t_stats[single_symbol]['t20'],
                        't20_pct': t_stats[single_symbol]['t20_pct'],
                        's_n': t_stats[single_symbol]['s_n']
                    }
                else:
                    single_symbol_check['checks']['t_filter'] = False
                    single_symbol_check['status'] = 'failed'
                    single_symbol_check['failed_at'] = 't_filter'
                    
                    # 計算該幣種的 T 值（即使未通過篩選）
                    if single_symbol in rs_filtered:
                        t20, t20_signed, s_n = t_calculator.calculate_t_value(
                            rs_filtered[single_symbol], 
                            config.T_MAIN_WINDOW
                        )
                        
                        reasons = []
                        if s_n <= 0:
                            reasons.append(f'S(N) = {s_n:.1f} ≤ 0（非上升趨勢）')
                        else:
                            # 計算百分位
                            t_values_all = {}
                            for sym, df in rs_filtered.items():
                                t_val, _, s_val = t_calculator.calculate_t_value(df, config.T_MAIN_WINDOW)
                                if s_val > 0:
                                    t_values_all[sym] = t_val
                            
                            if t_values_all:
                                all_t = list(t_values_all.values())
                                t20_pct = (sum(v < t20 for v in all_t) / len(all_t)) * 100
                                
                                if t20_pct < config.T_THRESHOLD:
                                    reasons.append(f'T(20) 百分位 {t20_pct:.1f}% < {config.T_THRESHOLD}%')
                        
                        single_symbol_check['message'] = '未通過 T 值篩選：' + ('、'.join(reasons) if reasons else '未知原因')
                        single_symbol_check['t_stats'] = {
                            't20': t20,
                            's_n': s_n
                        }
                    
                    return pd.DataFrame(), stats, single_symbol_check
            
            if not t_filtered:
                return pd.DataFrame(), stats, single_symbol_check
            
            # 9. T(10) 穩定性
            for symbol in t_filtered.keys():
                t10_stable = t_calculator.calculate_t10_stable(t_filtered[symbol])
                t_stats[symbol]['t10_stable'] = t10_stable
            
            # 10. 加分維度
            scoring_engine = ScoringEngine(btc_df)
            metrics = scoring_engine.calculate_all_metrics(t_filtered)
            
            # 11. 最終評分
            df_scores = scoring_engine.calculate_final_scores(
                rs_stats, t_stats, delta_rs, metrics
            )
            
            # 12. 加入額外資訊
            for idx, row in df_scores.iterrows():
                symbol = row['symbol']
                df_scores.at[idx, 't10_stable'] = t_stats[symbol].get('t10_stable', False)
                df_scores.at[idx, 'tier'] = tiers.get(symbol, 'all')
                
                if symbol in t_filtered:
                    df_scores.at[idx, 'close'] = t_filtered[symbol].iloc[-1]['close']
            
            # 單幣種檢查：最終入選
            if single_symbol and single_symbol_check:
                if single_symbol in df_scores['symbol'].values:
                    single_symbol_check['checks']['final_selected'] = True
                    single_symbol_check['status'] = 'success'
                    
                    # 找到該幣種的排名
                    rank = df_scores[df_scores['symbol'] == single_symbol].index[0] + 1
                    final_score = df_scores[df_scores['symbol'] == single_symbol]['final_score'].values[0]
                    
                    single_symbol_check['rank'] = rank
                    single_symbol_check['final_score'] = final_score
                    single_symbol_check['message'] = f'入選！排名第 {rank} 名，評分 {final_score:.1f}'
                else:
                    # 通過所有篩選但未入選（理論上不應該發生）
                    single_symbol_check['checks']['final_selected'] = False
                    single_symbol_check['status'] = 'failed'
                    single_symbol_check['failed_at'] = 'final_scoring'
                    single_symbol_check['message'] = '通過所有篩選但未入選（評分過低）'
            
            logger.info(f"回測完成：最終候選 {len(df_scores)} 個")
            
            return df_scores, stats, single_symbol_check
            
        except Exception as e:
            logger.error(f"回測執行失敗: {type(e).__name__} - {e}")
            raise
    
    def calculate_review(
        self,
        df_scores: pd.DataFrame,
        target_date: datetime,
        future_days: int = None
    ) -> Tuple[list, Optional[Dict]]:
        """
        計算篩選結果的未來表現回顧（MDD / 最大收益）
        
        Args:
            df_scores: 篩選結果 DataFrame（需包含 symbol, close 欄位）
            target_date: 篩選日期（GMT+8）
            future_days: 回顧天數（預設取 config.REVIEW_FUTURE_DAYS）
            
        Returns:
            (各幣種回顧列表, BTC 回顧字典)
        """
        import time
        
        if future_days is None:
            future_days = config.REVIEW_FUTURE_DAYS
        
        logger.info(f"開始計算數據回顧（未來 {future_days} 日）...")
        
        # BTC 回顧
        btc_review = self._fetch_symbol_review('BTCUSDT', target_date, future_days)
        
        # 各幣種回顧（依排名順序）
        review_rows = []
        for _, row in df_scores.iterrows():
            symbol = row['symbol']
            review = self._fetch_symbol_review(symbol, target_date, future_days)
            
            if review:
                # 使用回測結果中的收盤價作為入場價（更精確）
                if 'close' in row and pd.notna(row.get('close')):
                    review['entry_price'] = float(row['close'])
                review_rows.append(review)
            else:
                # 即使拉取失敗也保留佔位，保持排名順序
                review_rows.append({
                    'symbol': symbol,
                    'entry_price': float(row['close']) if 'close' in row and pd.notna(row.get('close')) else None,
                    'mdd': None, 'lowest': None,
                    'mp': None, 'highest': None,
                    'future_days': 0,
                })
            
            time.sleep(config.API_REQUEST_DELAY)
        
        logger.info(f"數據回顧計算完成：{len(review_rows)} 個幣種")
        return review_rows, btc_review
    
    def _fetch_symbol_review(
        self,
        symbol: str,
        target_date: datetime,
        future_days: int
    ) -> Optional[Dict]:
        """
        拉取單一幣種的未來數據並計算 MDD / 最大收益
        
        T0 收盤價為入場價，T1–T(N) 的最低 / 最高價計算回撤與收益
        """
        try:
            # T0 收盤時間 = target_date(GMT+8 00:00) → UTC 前日 16:00
            t0_utc = target_date - timedelta(hours=8)
            t0_utc = t0_utc.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # 拉取 T0 至 T0+N 的日線
            end_utc = t0_utc + timedelta(days=future_days + 1)
            
            klines = self.fetcher.client.futures_klines(
                symbol=symbol,
                interval=Client.KLINE_INTERVAL_1DAY,
                startTime=int(t0_utc.timestamp() * 1000),
                endTime=int(end_utc.timestamp() * 1000),
                limit=future_days + 2
            )
            
            if not klines or len(klines) < 2:
                return None
            
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # T0 = 第一根 K 線的收盤價
            entry_price = float(df.iloc[0]['close'])
            
            # T1 – T(N) = 後續 K 線
            future_df = df.iloc[1:]
            if len(future_df) == 0:
                return None
            
            lowest = float(future_df['low'].min())
            highest = float(future_df['high'].max())
            
            mdd = (lowest - entry_price) / entry_price * 100   # 負數
            mp  = (highest - entry_price) / entry_price * 100   # 正數
            
            return {
                'symbol': symbol,
                'entry_price': entry_price,
                'mdd': mdd,
                'lowest': lowest,
                'mp': mp,
                'highest': highest,
                'future_days': len(future_df),
            }
            
        except Exception as e:
            logger.warning(f"{symbol}: 計算回顧數據失敗: {type(e).__name__} - {e}")
            return None
