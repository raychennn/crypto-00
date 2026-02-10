"""
Telegram Bot 推送與命令處理
"""
import asyncio
import io
import re
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from screener.backtest import BacktestEngine
from utils import mask_secret, setup_logger

logger = setup_logger(__name__)

# 匹配 /YYMMDD 或 /YYMMDD SYMBOL（相容群組 @BotName 後綴）
_DATE_CMD_RE = re.compile(r'^/(\d{6})(?:@\S+)?\s*(.*)$')


# ─────────────────────────── 格式化工具 ───────────────────────────

def format_price(price: float) -> str:
    """依價格量級自動格式化"""
    if price is None or pd.isna(price):
        return "N/A"
    if price >= 1000:
        return f"${price:,.1f}"
    elif price >= 1:
        return f"${price:.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


# ─────────────────────────── Bot Handler ───────────────────────────

class TelegramBotHandler:
    """Telegram Bot 處理器（支援命令和推送）"""
    
    def __init__(self, screener_callback=None):
        if not config.TELEGRAM_BOT_TOKEN:
            raise ValueError("缺少 TELEGRAM_BOT_TOKEN")
        
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.allowed_users = config.TELEGRAM_ALLOWED_USERS
        self.screener_callback = screener_callback
        
        self.application = Application.builder().token(self.bot_token).build()
        
        # 註冊命令處理器（順序重要：先匹配具名命令，最後兜底）
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("now", self.cmd_now))
        # 兜底：捕捉所有未匹配的 /命令（包含 /YYMMDD 日期查詢）
        self.application.add_handler(MessageHandler(filters.COMMAND, self.cmd_date))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info(f"Telegram Bot 初始化成功（Token: {mask_secret(self.bot_token)}）")
    
    def is_authorized(self, user_id: int) -> bool:
        if not self.allowed_users or len(self.allowed_users) == 0:
            return True
        return str(user_id) in self.allowed_users
    
    # ────────── 命令處理 ──────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理 /start 命令"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ 您沒有權限使用此 Bot")
            return
        
        welcome_msg = (
            "👋 歡迎使用加密貨幣強勢幣篩選系統！\n\n"
            "可用命令：\n"
            "/now - 立即執行篩選\n"
            "/250209 - 查詢 2025/02/09 的篩選結果\n"
            "/250209 ETHUSDT - 查詢 ETHUSDT 在該日是否入選\n"
            "/help - 顯示幫助訊息"
        )
        await update.message.reply_text(welcome_msg)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理 /help 命令"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ 您沒有權限使用此 Bot")
            return
        
        help_msg = (
            "<b>📖 命令說明</b>\n\n"
            "<b>/now</b>\n"
            "立即執行一次完整篩選，回傳報告 + TradingView 觀察清單\n\n"
            "<b>/YYMMDD</b>\n"
            "查詢指定日期的篩選結果（回測）+ 未來一周數據回顧\n"
            "例如：<code>/250209</code> 查詢 2025/02/09\n"
            "⚠️ 使用 GMT+8 時區，查詢當日已收盤數據\n\n"
            "<b>/YYMMDD SYMBOL</b>\n"
            "檢查特定幣種在指定日期是否入選\n"
            "例如：<code>/250209 ETHUSDT</code>\n"
            "若未入選，會顯示卡在哪一關\n\n"
            "<b>注意事項：</b>\n"
            "• 查詢範圍取決於幣安 API 可用的歷史數據\n"
            "• 命令執行時間約 2-5 分鐘，請耐心等待\n"
            "• 系統每日 08:00 (GMT+8) 自動執行篩選並推送"
        )
        await update.message.reply_text(help_msg, parse_mode='HTML')
    
    async def cmd_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理 /now 命令：立即執行篩選"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ 您沒有權限使用此 Bot")
            return
        
        processing_msg = await update.message.reply_text("⏳ 正在執行篩選，請稍候...")
        
        try:
            if self.screener_callback:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self.screener_callback)
                df_scores, stats = result
                
                await self.send_screening_results_async(
                    update.effective_chat.id, df_scores, stats, is_realtime=True
                )
                await processing_msg.delete()
            else:
                await processing_msg.edit_text("❌ 篩選功能未配置")
                
        except Exception as e:
            error_msg = f"❌ 執行篩選時發生錯誤：\n{type(e).__name__}: {str(e)}"
            logger.error(f"cmd_now 執行失敗: {e}")
            logger.error(traceback.format_exc())
            await processing_msg.edit_text(error_msg)

    async def cmd_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        處理日期回測命令：/YYMMDD 或 /YYMMDD SYMBOL
        兜底所有未被具名 CommandHandler 匹配的命令。
        """
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ 您沒有權限使用此 Bot")
            return

        text = update.message.text.strip()
        match = _DATE_CMD_RE.match(text)

        if not match:
            await update.message.reply_text(
                "❌ 無法辨識的命令\n"
                "日期查詢請使用 YYMMDD 格式，例如：<code>/250209</code>\n"
                "輸入 /help 查看所有可用命令",
                parse_mode='HTML'
            )
            return

        date_str = match.group(1)
        symbol_arg = match.group(2).strip()

        # 解析日期
        try:
            year  = 2000 + int(date_str[:2])
            month = int(date_str[2:4])
            day   = int(date_str[4:6])
            target_date = datetime(year, month, day)
        except ValueError:
            await update.message.reply_text(
                f"❌ 日期格式錯誤：<code>{date_str}</code>\n"
                "請使用 YYMMDD 格式，例如：<code>/250209</code> 表示 2025/02/09",
                parse_mode='HTML'
            )
            return

        days_ago = (datetime.now() - target_date).days
        if days_ago < 0:
            await update.message.reply_text("❌ 不能查詢未來日期")
            return
        if config.BACKTEST_MAX_DAYS > 0 and days_ago > config.BACKTEST_MAX_DAYS:
            await update.message.reply_text(
                f"❌ 只支援查詢過去 {config.BACKTEST_MAX_DAYS} 天內的資料"
            )
            return

        # 解析幣種
        single_symbol = None
        if symbol_arg:
            single_symbol = symbol_arg.upper()
            if not single_symbol.endswith('USDT'):
                single_symbol += 'USDT'

        # 處理中訊息
        if single_symbol:
            processing_msg = await update.message.reply_text(
                f"⏳ 正在查詢 {single_symbol} 在 {target_date.strftime('%Y/%m/%d')} 的篩選結果..."
            )
        else:
            processing_msg = await update.message.reply_text(
                f"⏳ 正在查詢 {target_date.strftime('%Y/%m/%d')} 的篩選結果..."
            )

        try:
            loop = asyncio.get_event_loop()

            # 1) 執行回測
            result = await loop.run_in_executor(
                None, self.run_backtest_sync, target_date, single_symbol
            )
            df_scores, stats, single_check = result

            if single_symbol:
                # ── 單幣種檢查 ──
                await self.send_single_symbol_check(
                    update.effective_chat.id, single_check, target_date
                )
            else:
                # ── 全量回測 ──
                # 訊息 1：篩選報告 + 觀察清單
                await self.send_screening_results_async(
                    update.effective_chat.id, df_scores, stats,
                    is_realtime=False, target_date=target_date
                )

                # 訊息 2：數據回顧（有結果才計算）
                if len(df_scores) > 0:
                    try:
                        review_msg = await self.application.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="⏳ 正在計算數據回顧..."
                        )
                        review_result = await loop.run_in_executor(
                            None, self.run_review_sync, df_scores, target_date
                        )
                        review_rows, btc_review = review_result
                        review_text = format_review_message(
                            review_rows, btc_review, target_date
                        )
                        await review_msg.edit_text(review_text, parse_mode='HTML')
                    except Exception as e:
                        logger.warning(f"數據回顧計算失敗: {e}")
                        logger.warning(traceback.format_exc())
                        try:
                            await review_msg.edit_text(
                                f"⚠️ 數據回顧計算失敗：{type(e).__name__}: {e}"
                            )
                        except Exception:
                            pass

            await processing_msg.delete()

        except Exception as e:
            error_msg = f"❌ 執行查詢時發生錯誤：\n{type(e).__name__}: {str(e)}"
            logger.error(f"cmd_date 執行失敗: {e}")
            logger.error(traceback.format_exc())
            await processing_msg.edit_text(error_msg)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理一般文字訊息（非命令）"""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ 您沒有權限使用此 Bot")
            return
        pass
    
    # ────────── 同步包裝（供 run_in_executor 使用） ──────────

    def run_backtest_sync(self, target_date: datetime, single_symbol: Optional[str]):
        engine = BacktestEngine()
        return engine.run_backtest(target_date, single_symbol)
    
    def run_review_sync(self, df_scores: pd.DataFrame, target_date: datetime):
        engine = BacktestEngine()
        return engine.calculate_review(df_scores, target_date)
    
    # ────────── 發送結果 ──────────

    async def send_single_symbol_check(
        self, chat_id: str, check_result: dict, target_date: datetime
    ):
        """發送單幣種檢查結果"""
        symbol = check_result['symbol']
        status = check_result['status']
        date_str = target_date.strftime('%Y/%m/%d')
        
        if status == 'not_trading':
            message = (
                f"<b>🔍 {symbol} 檢查結果</b>\n"
                f"<b>日期：</b>{date_str}\n\n"
                f"❌ {check_result['message']}"
            )
        
        elif status == 'success':
            rank = check_result['rank']
            final_score = check_result['final_score']
            rs_stats = check_result.get('rs_stats', {})
            t_stats = check_result.get('t_stats', {})
            
            message = (
                f"<b>✅ {symbol} 檢查結果</b>\n"
                f"<b>日期：</b>{date_str}\n\n"
                f"<b>入選！排名第 {rank} 名</b>\n"
                f"<b>最終評分：</b>{final_score:.1f}\n\n"
                f"<b>RS 強度：</b>\n"
                f"  • RS(7): {rs_stats.get('rs7_pct', 0):.1f}%\n"
                f"  • RS(21): {rs_stats.get('rs21_pct', 0):.1f}%\n\n"
                f"<b>T 值：</b>\n"
                f"  • T(20): {t_stats.get('t20', 0):.4f}\n"
                f"  • T(20) 百分位: {t_stats.get('t20_pct', 0):.1f}%\n"
                f"  • S(N): {t_stats.get('s_n', 0):.1f}"
            )
        
        else:  # failed
            message_text = check_result.get('message', '未知原因')
            checks = check_result.get('checks', {})
            
            checklist = []
            if 'data_loaded' in checks:
                checklist.append(f"{'✅' if checks['data_loaded'] else '❌'} 數據載入")
            if 'base_filter' in checks:
                checklist.append(f"{'✅' if checks['base_filter'] else '❌'} 基礎過濾")
            if 'rs_filter' in checks:
                checklist.append(f"{'✅' if checks['rs_filter'] else '❌'} RS Rank 篩選")
                if 'rs_stats' in check_result:
                    rs = check_result['rs_stats']
                    checklist.append(
                        f"    RS(7): {rs.get('rs7_pct', 0):.1f}% "
                        f"RS(21): {rs.get('rs21_pct', 0):.1f}%"
                    )
            if 't_filter' in checks:
                checklist.append(f"{'✅' if checks['t_filter'] else '❌'} T 值篩選")
                if 't_stats' in check_result:
                    checklist.append(f"    S(N): {check_result['t_stats'].get('s_n', 0):.1f}")
            if 'final_selected' in checks:
                checklist.append(f"{'✅' if checks['final_selected'] else '❌'} 最終入選")
            
            message = (
                f"<b>❌ {symbol} 檢查結果</b>\n"
                f"<b>日期：</b>{date_str}\n\n"
                f"<b>未入選</b>\n\n"
                f"<b>檢查清單：</b>\n"
                + '\n'.join(checklist) + '\n\n'
                f"<b>失敗原因：</b>\n{message_text}"
            )
        
        await self.application.bot.send_message(
            chat_id=chat_id, text=message, parse_mode='HTML'
        )
    
    async def send_screening_results_async(
        self,
        chat_id: str,
        df_scores: pd.DataFrame,
        stats: dict,
        is_realtime: bool = True,
        target_date: Optional[datetime] = None
    ):
        """非同步發送篩選結果 + TradingView 觀察清單"""
        try:
            message = format_report_message(df_scores, stats, is_realtime, target_date)
            
            await self.application.bot.send_message(
                chat_id=chat_id, text=message,
                parse_mode='HTML', disable_web_page_preview=True
            )
            
            # 生成並發送 TradingView 觀察清單
            if len(df_scores) > 0:
                output_dir = Path(config.DATA_DIR) / "results"
                output_dir.mkdir(parents=True, exist_ok=True)
                
                watchlist_file = generate_tradingview_watchlist(
                    df_scores, output_dir, target_date
                )
                
                with open(watchlist_file, 'rb') as f:
                    await self.application.bot.send_document(
                        chat_id=chat_id, document=f,
                        filename=watchlist_file.name,
                        caption=f"TradingView 觀察清單（共 {len(df_scores)} 個幣種）"
                    )
            
        except Exception as e:
            logger.error(f"發送篩選結果失敗: {e}")
            raise
    
    async def run_polling(self):
        """啟動 Bot 輪詢模式"""
        logger.info("Telegram Bot 開始輪詢...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
    
    async def send_scheduled_report(self, df_scores: pd.DataFrame, stats: dict):
        """發送定時報告（給指定的 Chat ID）"""
        if not self.chat_id:
            logger.warning("未設定 TELEGRAM_CHAT_ID，跳過推送")
            return
        await self.send_screening_results_async(
            self.chat_id, df_scores, stats, is_realtime=True
        )


# ─────────────────────── 訊息格式化函式 ───────────────────────

def format_report_message(
    df_scores: pd.DataFrame,
    stats: dict,
    is_realtime: bool = True,
    target_date: Optional[datetime] = None
) -> str:
    """格式化篩選報告訊息"""
    if target_date:
        date_str = target_date.strftime('%Y-%m-%d')
        title = f"📊 <b>強勢幣篩選報告（回測）</b>\n<b>日期：</b>{date_str}"
    else:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        title = f"📊 <b>強勢幣篩選報告 {today}</b>"
    
    lines = [
        title,
        "",
        f"<b>掃描範圍：</b>幣安 U 本位永續合約",
        f"<b>通過基礎過濾：</b>{stats.get('base_filtered', 0)} 個",
        f"<b>通過 RS 篩選：</b>{stats.get('rs_filtered', 0)} 個",
        f"<b>通過 T 值篩選：</b>{stats.get('t_filtered', 0)} 個",
        f"<b>最終候選：</b>{len(df_scores)} 個",
    ]
    
    if len(df_scores) == 0:
        lines.append("\n今日無符合條件的幣種")
        return '\n'.join(lines)
    
    lines.extend([
        "",
        "<b>排名 | 幣種 | 評分 | RS(7) | T(20) | 量比 | ΔRS</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ])
    
    top_n = min(config.TOP_N_DISPLAY, len(df_scores))
    
    for idx, row in df_scores.head(top_n).iterrows():
        symbol = row['symbol'].replace('USDT', '')
        score = row['final_score']
        rs7 = row['rs7_pct']
        t20 = row['t20_pct']
        vol_ratio = row.get('vol_ratio')
        delta_rs = row.get('delta_rs')
        
        vol_str = f"{vol_ratio:.1f}x" if pd.notna(vol_ratio) else "N/A"
        drs_str = f"{delta_rs:+.0f}" if pd.notna(delta_rs) else "N/A"
        
        markers = []
        if row.get('t10_stable', False):
            markers.append('🟢')
        if row.get('atr_expanding', False):
            markers.append('⚡')
        marker_str = ' '.join(markers) if markers else ''
        
        line = (
            f"{idx+1}. <code>{symbol:8s}</code> "
            f"{score:5.1f}  "
            f"{rs7:3.0f}%  "
            f"{t20:3.0f}%  "
            f"{vol_str:>5s}  "
            f"{drs_str:>4s} "
            f"{marker_str}"
        )
        lines.append(line)
    
    lines.extend([
        "",
        "<b>標記說明：</b>",
        "🟢 = 趨勢品質穩定（T(10) 未衰減）",
        "⚡ = 波動率突破（從壓縮展開）"
    ])
    
    if not is_realtime:
        lines.append("\n⚠️ 回測結果不含 ΔRS（排名變化速度）")
    
    return '\n'.join(lines)


def format_review_message(
    review_rows: list,
    btc_review: Optional[dict],
    target_date: datetime
) -> str:
    """
    格式化數據回顧訊息（第二則 Telegram 訊息）
    
    顯示每個入選幣種在篩選日之後 7 日的 MDD 與最大收益，
    以及同期 BTC 的基準表現。
    """
    date_str = target_date.strftime('%Y/%m/%d')
    future_days = config.REVIEW_FUTURE_DAYS

    lines = [
        f"📈 <b>數據回顧（T0 後 {future_days} 日表現）</b>",
        f"<b>日期：</b>{date_str}",
        "",
    ]

    # ── BTC 基準 ──
    if btc_review and btc_review.get('mdd') is not None:
        actual_days = btc_review['future_days']
        day_note = f"（僅 {actual_days} 日數據）" if actual_days < future_days else ""
        
        lines.append(f"<b>📌 BTC 基準</b>{day_note}")
        lines.append(f"  入場：{format_price(btc_review['entry_price'])}")
        lines.append(
            f"  MDD：{btc_review['mdd']:.2f}%"
            f"（最低 {format_price(btc_review['lowest'])}）"
        )
        lines.append(
            f"  MP：{btc_review['mp']:+.2f}%"
            f"（最高 {format_price(btc_review['highest'])}）"
        )
    else:
        lines.append("<b>📌 BTC 基準</b>：未來數據不足")

    lines.extend([
        "",
        "<b>排名 | 幣種 | 入場價 | MDD(最低) | MP(最高)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ])

    # ── 各幣種 ──
    for i, row in enumerate(review_rows, 1):
        symbol = row['symbol'].replace('USDT', '')
        entry = format_price(row.get('entry_price'))

        if row.get('mdd') is not None:
            mdd_str  = f"{row['mdd']:.1f}%"
            low_str  = format_price(row['lowest'])
            mp_str   = f"{row['mp']:+.1f}%"
            high_str = format_price(row['highest'])
            line = (
                f"{i}. <code>{symbol:8s}</code> {entry}  "
                f"{mdd_str}({low_str})  {mp_str}({high_str})"
            )
        else:
            line = f"{i}. <code>{symbol:8s}</code> {entry}  數據不足"

        lines.append(line)

    # ── 數據不足提示 ──
    valid_rows = [r for r in review_rows if r.get('future_days', 0) > 0]
    if valid_rows:
        actual = valid_rows[0]['future_days']
        if actual < future_days:
            lines.append(f"\n⚠️ 距今不足 {future_days} 日，僅顯示 {actual} 日數據")

    return '\n'.join(lines)


# ──────────────────────── TradingView 觀察清單 ────────────────────────

def generate_tradingview_watchlist(
    df_scores: pd.DataFrame,
    output_dir: Path,
    target_date: Optional[datetime] = None
) -> Path:
    """生成 TradingView 觀察清單檔案（T0_yyyy-mm-dd.txt）"""
    if target_date:
        date_str = target_date.strftime('%Y-%m-%d')
    else:
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    filename = f"T0_{date_str}.txt"
    filepath = output_dir / filename
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    tv_lines = [f"BINANCE:{row['symbol']}.P" for _, row in df_scores.iterrows()]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(tv_lines))
    
    logger.info(f"TradingView 觀察清單已生成: {filepath}")
    return filepath
