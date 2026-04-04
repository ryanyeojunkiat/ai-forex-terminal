"""
AlphaEdge Gold Signals — Main Orchestrator

XAUUSD-only automated signal platform.
Scans gold → generates signals → executes on MT5 → broadcasts via Telegram.

Run: python main.py
"""
import os
import sys
import time
import logging
import signal as sig
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    METAAPI_TOKEN, TWELVE_DATA_KEY,
    SYMBOL, SYMBOL_PIP, PLATFORM_NAME,
    ADMIN_TELEGRAM_IDS, GROUP_INVITE_LINK,
)
from trade_manager import TradeManager
from telegram_bot import TelegramNotifier, CommandHandler, start_polling, send_message
from mt5_executor import MT5Executor, TradeExecutionBridge
from price_feed import GoldPriceFeed
from signal_engine import GoldSignalEngine
from risk_manager import RiskManager

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("alpha_edge_gold.log"),
    ],
)
logger = logging.getLogger("alphaedge.main")


class AlphaEdgeGold:
    """
    Gold-only signal platform.
    One asset. Full focus. Maximum edge.
    """

    def __init__(self):
        # Core
        self.trade_manager = TradeManager()
        self.risk_manager = RiskManager(balance=10000)

        # MT5
        self.mt5 = MT5Executor()
        self.execution_bridge = TradeExecutionBridge(self.mt5)

        # Telegram
        self.notifier = TelegramNotifier()
        self.command_handler = CommandHandler(
            trade_manager=self.trade_manager,
            notifier=self.notifier,
            admin_ids=ADMIN_TELEGRAM_IDS,
            group_invite_link=GROUP_INVITE_LINK,
        )

        # Signal engine (gold only)
        self.signal_engine = GoldSignalEngine(on_signal=self._on_new_signal)

        # Price feed (gold only)
        self.price_feed = GoldPriceFeed(
            on_tick=self._on_price_tick,
            interval=2.0,
        )

        # State
        self._running = False
        self._scan_interval = 300  # Scan every 5 min
        self._last_scan = 0

    def start(self):
        """Start the gold signal platform."""
        logger.info("=" * 50)
        logger.info(f"{PLATFORM_NAME} starting...")
        logger.info("Asset: XAUUSD (Gold) — ONLY")
        logger.info("=" * 50)

        self._running = True
        self._validate_config()
        self._sync_balance()

        # Start price feed
        self.price_feed.start()

        # Start Telegram polling
        if TELEGRAM_BOT_TOKEN:
            tg_thread = threading.Thread(
                target=start_polling,
                args=(self.command_handler,),
                daemon=True,
            )
            tg_thread.start()
            logger.info("Telegram bot started")

            send_message(
                TELEGRAM_CHANNEL_ID,
                f"🥇 <b>{PLATFORM_NAME} is ONLINE</b>\n"
                f"{'━' * 28}\n"
                f"Asset: XAUUSD (Gold)\n"
                f"Risk: {self.risk_manager.risk_pct}% per trade\n"
                f"Max trades: {self.risk_manager.max_trades}\n"
                f"10-level TP system active\n"
                f"{'━' * 28}"
            )

        logger.info("Platform ready — entering main loop")
        self._main_loop()

    def stop(self):
        """Shut down."""
        logger.info("Shutting down...")
        self._running = False
        self.price_feed.stop()

        if TELEGRAM_BOT_TOKEN:
            send_message(
                TELEGRAM_CHANNEL_ID,
                f"🔴 <b>{PLATFORM_NAME} is OFFLINE</b>\n"
                "Active gold trades continue on MT5."
            )

        logger.info("Shutdown complete")

    def _main_loop(self):
        while self._running:
            try:
                now = time.time()
                if now - self._last_scan >= self._scan_interval:
                    self._last_scan = now
                    self._run_signal_scan()
                time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                time.sleep(5)

    def _on_price_tick(self, prices):
        """Called every 2 seconds with gold price."""
        if not self.trade_manager.active_trades:
            return

        actions = self.trade_manager.check_all_prices(prices)

        if actions:
            exec_results = self.execution_bridge.process_actions(actions)
            for r in exec_results:
                if not r.get("success"):
                    logger.error(f"MT5 execution failed: {r}")

            self.notifier.process_actions(actions)

            for action in actions:
                if action["action"] in ("CLOSE_ALL", "FULLY_CLOSED"):
                    trade = action.get("trade")
                    if trade:
                        sl_pips = abs(trade.entry - trade.sl_original) / SYMBOL_PIP
                        self.risk_manager.unregister_trade(trade.lot_total, sl_pips)

    def _on_new_signal(self, signal):
        """Called when signal engine finds a gold opportunity."""
        direction = signal["direction"]
        entry = signal["entry"]
        sl = signal["sl"]

        logger.info(
            f"GOLD SIGNAL: {direction} @ {entry:.2f}, SL={sl:.2f}, "
            f"Score={signal['score']}, Session={signal.get('session')}"
        )

        if not self.risk_manager.can_open_trade():
            logger.warning("Risk limit reached — skipping signal")
            return

        lot = self.risk_manager.calculate_lot_size(entry, sl)

        trade = self.trade_manager.open_trade(
            symbol=SYMBOL,
            direction=direction,
            entry=entry,
            sl=sl,
            lot=lot,
            source="auto",
        )

        ticket = self.execution_bridge.execute_open(trade)
        if not ticket:
            logger.error("MT5 execution failed — signal still broadcast")

        sl_pips = abs(entry - sl) / SYMBOL_PIP
        self.risk_manager.register_trade(lot, sl_pips)
        self.notifier.broadcast_signal(trade)

        logger.info(f"Trade opened: {trade.id} | {direction} XAUUSD | Lot {lot} | Ticket {ticket}")

    def _run_signal_scan(self):
        """Scan gold during market hours."""
        now_utc = datetime.now(timezone.utc)
        weekday = now_utc.weekday()
        hour = now_utc.hour

        # Skip weekends
        if weekday == 5:
            return
        if weekday == 6 and hour < 22:
            return
        if weekday == 4 and hour >= 22:
            return

        logger.info(f"Scanning XAUUSD at {now_utc.strftime('%H:%M')} UTC")
        signal = self.signal_engine.scan()
        if signal:
            logger.info(f"Signal found! Score: {signal['score']}")
        else:
            logger.info("No signal — conditions not met")

    def _sync_balance(self):
        if not METAAPI_TOKEN:
            return
        try:
            info = self.mt5.get_account_info()
            if info and "balance" in info:
                self.risk_manager.update_balance(info["balance"])
                logger.info(f"Balance synced: USD {info['balance']:.2f}")
        except Exception as e:
            logger.error(f"Balance sync error: {e}")

    def _validate_config(self):
        warnings = []
        if not TELEGRAM_BOT_TOKEN:
            warnings.append("TELEGRAM_BOT_TOKEN not set — Telegram disabled")
        if not TELEGRAM_CHANNEL_ID:
            warnings.append("TELEGRAM_CHANNEL_ID not set — broadcasts disabled")
        if not METAAPI_TOKEN:
            warnings.append("METAAPI_TOKEN not set — MT5 execution disabled")
        if not TWELVE_DATA_KEY:
            warnings.append("TWELVE_DATA_API_KEY not set — signal engine limited")

        for w in warnings:
            logger.warning(w)


def main():
    platform = AlphaEdgeGold()

    def shutdown(signum, frame):
        platform.stop()
        sys.exit(0)

    sig.signal(sig.SIGINT, shutdown)
    sig.signal(sig.SIGTERM, shutdown)

    platform.start()


if __name__ == "__main__":
    main()
