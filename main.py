"""
加密貨幣強勢幣篩選系統
程式進入點：整合排程器與 Telegram Bot
"""
import asyncio
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from bot.telegram import TelegramBotHandler
from screener import (
    BinanceDataFetcher,
    RSRankCalculator,
    ScoringEngine,
    TValueCalculator,
    apply_base_filters,
    assign_tiers,
    preprocess_data,
)
from utils import mask_secret, setup_logger

logger = setup_logger(__name__)


def validate_environment():
    """驗證環境變數是否齊全"""
    required_vars = {
        'BINANCE_API_KEY': config.BINANCE_API_KEY,
        'BINANCE_API_SECRET': config.BINANCE_API_SECRET,
        'TELEGRAM_BOT_TOKEN': config.TELEGRAM_BOT_TOKEN,
    }
    
    missing = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing.append(var_name)
        else:
            logger.info(f"{var_name}: {mask_secret(var_value)}")
    
    if missing:
        error_msg = f"缺少必要的環境變數: {', '.join(missing)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("環境變數驗證通過")


def run_screener_sync() -> tuple:
    """
    執行完整的篩選流程（同步版本，用於命令回調）
    
    Returns:
        (df_scores, stats)
    """
    logger.info("=" * 60)
    logger.info("開始執行篩選流程")
    logger.info("=" * 60)
    
    stats = {}
    
    try:
        # 初始化數據拉取器
        logger.info("初始化幣安數據拉取器...")
        fetcher = BinanceDataFetcher()
        
        # 1. 獲取所有交易對
        logger.info("獲取所有 USDT 永續合約交易對...")
        all_symbols = fetcher.get_all_usdt_perpetual_symbols()
        stats['total_symbols'] = len(all_symbols)
        
        # 2. 拉取 BTC 數據（作為基準）
        logger.info("拉取 BTCUSDT 數據...")
        btc_df = fetcher.fetch_klines('BTCUSDT')
        
        if btc_df is None or len(btc_df) < config.MIN_LISTING_DAYS:
            raise ValueError(
                f"無法獲取足夠的 BTCUSDT 歷史數據"
                f"（取得 {len(btc_df) if btc_df is not None else 0} 根，"
                f"需要至少 {config.MIN_LISTING_DAYS} 根）"
            )
        
        btc_df, _ = preprocess_data(btc_df, 'BTCUSDT')
        logger.info(f"BTCUSDT 數據載入完成（{len(btc_df)} 根 K 線）")
        
        # 3. 拉取所有幣種數據
        logger.info(f"開始拉取 {len(all_symbols)} 個幣種的 K 線數據...")
        data_dict = {}
        
        for i, symbol in enumerate(all_symbols, 1):
            if i % 50 == 0:
                logger.info(f"進度: {i}/{len(all_symbols)}")
            
            try:
                df = fetcher.fetch_klines(symbol)
                
                if df is not None and len(df) >= config.MIN_LISTING_DAYS:
                    df_processed, data_ok = preprocess_data(df, symbol)
                    
                    if data_ok:
                        data_dict[symbol] = df_processed
                        
            except Exception as e:
                logger.warning(f"{symbol}: 拉取數據時發生錯誤: {type(e).__name__} - {e}")
                continue
        
        logger.info(f"成功載入 {len(data_dict)} 個幣種的數據")
        stats['loaded_symbols'] = len(data_dict)
        
        # 4. 應用基礎過濾
        logger.info("應用基礎過濾...")
        filtered_data = apply_base_filters(data_dict)
        stats['base_filtered'] = len(filtered_data)
        
        if not filtered_data:
            logger.warning("無幣種通過基礎過濾，結束流程")
            return pd.DataFrame(), stats
        
        # 5. 分配市值層級（可選）
        logger.info("分配市值層級...")
        tiers = assign_tiers(filtered_data)
        
        # 6. RS Rank 篩選
        logger.info("計算 RS Rank 並篩選...")
        rs_calculator = RSRankCalculator(btc_df)
        
        # ★ 自動回推 ΔRS 歷史資料（若啟用）
        if config.AUTO_BACKFILL_RS_HISTORY:
            rs_calculator.backfill_history(filtered_data)
        
        rs_filtered, rs_stats = rs_calculator.filter_by_rs_rank(filtered_data)
        stats['rs_filtered'] = len(rs_filtered)
        
        if not rs_filtered:
            logger.warning("無幣種通過 RS 篩選，結束流程")
            return pd.DataFrame(), stats
        
        # 7. 計算 ΔRS
        logger.info("計算 ΔRS（RS 排名變化速度）...")
        current_rs7_pct = {s: rs_stats[s]['rs7_pct'] for s in rs_stats.keys()}
        delta_rs = rs_calculator.calculate_delta_rs(current_rs7_pct)
        
        # 8. T 值篩選
        logger.info("計算 T 值並篩選...")
        t_calculator = TValueCalculator()
        t_filtered, t_stats = t_calculator.filter_by_t_value(rs_filtered)
        stats['t_filtered'] = len(t_filtered)
        
        if not t_filtered:
            logger.warning("無幣種通過 T 值篩選，結束流程")
            return pd.DataFrame(), stats
        
        # 9. 計算 T(10) 穩定性
        logger.info("計算 T(10) 穩定性...")
        for symbol in t_filtered.keys():
            t10_stable = t_calculator.calculate_t10_stable(t_filtered[symbol])
            t_stats[symbol]['t10_stable'] = t10_stable
        
        # 10. 計算加分維度指標
        logger.info("計算加分維度指標...")
        scoring_engine = ScoringEngine(btc_df)
        metrics = scoring_engine.calculate_all_metrics(t_filtered)
        
        # 11. 計算最終評分
        logger.info("計算最終加權評分...")
        df_scores = scoring_engine.calculate_final_scores(
            rs_stats, t_stats, delta_rs, metrics
        )
        
        # 12. 加入額外資訊
        for idx, row in df_scores.iterrows():
            symbol = row['symbol']
            df_scores.at[idx, 't10_stable'] = t_stats[symbol].get('t10_stable', False)
            df_scores.at[idx, 'tier'] = tiers.get(symbol, 'all')
            
            # 加入收盤價
            if symbol in t_filtered:
                df_scores.at[idx, 'close'] = t_filtered[symbol].iloc[-1]['close']
        
        # 13. 儲存 CSV
        output_dir = Path(config.DATA_DIR) / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.utcnow().strftime('%Y-%m-%d')
        csv_path = output_dir / f"screener_{today}.csv"
        df_scores.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f"結果已儲存至 {csv_path}")
        
        logger.info("=" * 60)
        logger.info("篩選流程執行完成")
        logger.info("=" * 60)
        
        return df_scores, stats
        
    except Exception as e:
        error_msg = f"篩選流程發生未預期錯誤: {type(e).__name__} - {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise


async def run_screener_and_notify(bot_handler: TelegramBotHandler):
    """
    執行篩選並透過 Telegram 推送結果（用於定時任務）
    
    Args:
        bot_handler: Telegram Bot 處理器
    """
    try:
        logger.info("定時任務觸發：開始執行篩選")
        
        # 在線程池中執行篩選（避免阻塞事件循環）
        loop = asyncio.get_event_loop()
        df_scores, stats = await loop.run_in_executor(None, run_screener_sync)
        
        # 發送結果
        if config.TELEGRAM_CHAT_ID:
            await bot_handler.send_scheduled_report(df_scores, stats)
        else:
            logger.warning("未設定 TELEGRAM_CHAT_ID，跳過推送")
        
    except Exception as e:
        error_msg = f"定時篩選任務失敗: {type(e).__name__} - {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        # 嘗試發送錯誤通知
        if config.TELEGRAM_CHAT_ID and bot_handler:
            try:
                await bot_handler.application.bot.send_message(
                    chat_id=config.TELEGRAM_CHAT_ID,
                    text=f"❌ <b>篩選系統錯誤</b>\n\n{error_msg}",
                    parse_mode='HTML'
                )
            except Exception as notify_error:
                logger.error(f"發送錯誤通知失敗: {notify_error}")


async def main():
    """主函式：啟動排程器和 Telegram Bot"""
    try:
        logger.info("加密貨幣強勢幣篩選系統啟動")
        
        # 驗證環境變數
        validate_environment()
        
        # 初始化 Telegram Bot（傳入篩選回調函式）
        bot_handler = TelegramBotHandler(screener_callback=run_screener_sync)
        
        # 初始化非同步排程器
        scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
        
        # 註冊定時任務
        trigger = CronTrigger(
            hour=config.SCHEDULE_HOUR,
            minute=config.SCHEDULE_MINUTE,
            timezone=config.TIMEZONE
        )
        scheduler.add_job(
            run_screener_and_notify,
            trigger=trigger,
            args=[bot_handler],
            id='daily_screener',
            name='每日篩選任務',
            replace_existing=True
        )
        
        logger.info(
            f"排程器已設定：每日 {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} "
            f"({config.TIMEZONE}) 執行篩選"
        )
        
        # 啟動排程器
        scheduler.start()
        
        # 啟動時立即執行一次（可選）
        if config.RUN_ON_STARTUP:
            logger.info("啟動時立即執行篩選...")
            await run_screener_and_notify(bot_handler)
        
        # 啟動 Telegram Bot 輪詢
        logger.info("啟動 Telegram Bot...")
        await bot_handler.run_polling()
        
        # 保持運行
        while True:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在關閉...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"系統啟動失敗: {type(e).__name__} - {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    # 運行主函式
    asyncio.run(main())
