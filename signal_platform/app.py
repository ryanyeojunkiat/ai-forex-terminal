"""
AlphaEdge Gold Signals — Streamlit Cloud Dashboard

This wraps the signal bot in a Streamlit app so it can run 24/7 on Streamlit Cloud.
The bot runs in a background thread while Streamlit serves the admin dashboard.
"""
import os
import sys
import time
import json
import threading
import logging
import streamlit as st
from datetime import datetime, timezone

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
    METAAPI_TOKEN, TWELVE_DATA_KEY,
    SYMBOL, PLATFORM_NAME, ADMIN_TELEGRAM_IDS,
    GROUP_INVITE_LINK,
)
from trade_manager import TradeManager
from telegram_bot import (
    TelegramNotifier, CommandHandler, start_polling,
    send_message, _load_users,
)
from mt5_executor import MT5Executor, TradeExecutionBridge
from price_feed import GoldPriceFeed
from signal_engine import GoldSignalEngine
from risk_manager import RiskManager

# ── Page Config ──
st.set_page_config(
    page_title="AlphaEdge Gold Signals",
    page_icon="🥇",
    layout="wide",
)

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("alphaedge.app")


# ═══════════════════════════════════════════════════════════
#  BACKGROUND BOT — Runs in a thread
# ═══════════════════════════════════════════════════════════

def start_bot():
    """Start the full signal bot in a background thread."""
    # Core
    trade_manager = TradeManager()
    risk_manager = RiskManager(balance=10000)

    # MT5
    mt5 = MT5Executor()
    execution_bridge = TradeExecutionBridge(mt5)

    # Telegram
    notifier = TelegramNotifier()
    command_handler = CommandHandler(
        trade_manager=trade_manager,
        notifier=notifier,
        admin_ids=ADMIN_TELEGRAM_IDS,
        group_invite_link=GROUP_INVITE_LINK,
    )

    # Signal engine
    signal_engine = GoldSignalEngine()

    # Store in session state for dashboard access
    st.session_state["trade_manager"] = trade_manager
    st.session_state["risk_manager"] = risk_manager
    st.session_state["notifier"] = notifier
    st.session_state["signal_engine"] = signal_engine

    def on_price_tick(prices):
        if not trade_manager.active_trades:
            return
        actions = trade_manager.check_all_prices(prices)
        if actions:
            execution_bridge.process_actions(actions)
            notifier.process_actions(actions)

    def on_new_signal(signal):
        direction = signal["direction"]
        entry = signal["entry"]
        sl = signal["sl"]
        if not risk_manager.can_open_trade():
            return
        lot = risk_manager.calculate_lot_size(entry, sl)
        trade = trade_manager.open_trade("XAUUSD", direction, entry, sl, lot, source="auto")
        execution_bridge.execute_open(trade)
        from config import SYMBOL_PIP
        sl_pips = abs(entry - sl) / SYMBOL_PIP
        risk_manager.register_trade(lot, sl_pips)
        notifier.broadcast_signal(trade)

    signal_engine.on_signal = on_new_signal

    # Price feed
    price_feed = GoldPriceFeed(on_tick=on_price_tick, interval=2.0)
    price_feed.start()

    # Telegram polling
    if TELEGRAM_BOT_TOKEN:
        tg_thread = threading.Thread(
            target=start_polling,
            args=(command_handler,),
            daemon=True,
        )
        tg_thread.start()

        send_message(
            TELEGRAM_CHANNEL_ID,
            f"🥇 <b>{PLATFORM_NAME} is ONLINE</b>\n"
            f"{'━' * 28}\n"
            f"Asset: XAUUSD (Gold)\n"
            f"Mode: Streamlit Cloud 24/7\n"
            f"{'━' * 28}"
        )

    # Signal scan loop
    def scan_loop():
        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                weekday = now_utc.weekday()
                hour = now_utc.hour
                # Skip weekends
                if weekday == 5 or (weekday == 6 and hour < 22) or (weekday == 4 and hour >= 22):
                    time.sleep(60)
                    continue
                signal_engine.scan()
            except Exception as e:
                logger.error(f"Scan error: {e}")
            time.sleep(300)  # Every 5 min

    scan_thread = threading.Thread(target=scan_loop, daemon=True)
    scan_thread.start()

    # Sync balance
    if METAAPI_TOKEN:
        try:
            info = mt5.get_account_info()
            if info and "balance" in info:
                risk_manager.update_balance(info["balance"])
        except Exception:
            pass

    st.session_state["bot_started_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Bot started via Streamlit")


# ═══════════════════════════════════════════════════════════
#  START BOT (once per session)
# ═══════════════════════════════════════════════════════════

# Use a file-based flag so the bot only starts ONCE, even across page refreshes.
# st.session_state resets on meta-refresh, so we can't rely on it alone.
BOT_LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot_running")

def _is_bot_running():
    """Check if bot is already running (file-based lock)."""
    if os.path.exists(BOT_LOCK_FILE):
        try:
            with open(BOT_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if process is still alive
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, OSError):
            # Stale lock file — process died
            os.remove(BOT_LOCK_FILE)
            return False
    return False

def _mark_bot_running():
    """Write current PID to lock file."""
    with open(BOT_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

if not _is_bot_running():
    _mark_bot_running()
    start_bot()
    st.session_state["bot_running"] = True
else:
    st.session_state["bot_running"] = True


# ═══════════════════════════════════════════════════════════
#  DASHBOARD UI
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
#  PASSWORD PROTECTION — Only admin can see dashboard
# ═══════════════════════════════════════════════════════════

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "alphaedge2026")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("# 🥇 AlphaEdge Gold Signals")
    st.markdown("**Admin Login Required**")
    st.markdown("---")
    password = st.text_input("Enter admin password:", type="password")
    if st.button("Login", type="primary"):
        if password == ADMIN_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password. Try again.")
    st.stop()

st.markdown("# 🥇 AlphaEdge Gold Signals")
st.markdown("**XAUUSD Auto Signal Platform — Admin Dashboard**")
st.markdown("---")

# ── Status Bar ──
col1, col2, col3, col4 = st.columns(4)

with col1:
    bot_started = st.session_state.get("bot_started_at", "N/A")
    st.metric("Bot Status", "🟢 ONLINE")

with col2:
    tm = st.session_state.get("trade_manager")
    active_count = len(tm.active_trades) if tm else 0
    st.metric("Active Trades", active_count)

with col3:
    rm = st.session_state.get("risk_manager")
    if rm:
        st.metric("Balance", f"USD {rm.balance:,.2f}")
    else:
        st.metric("Balance", "N/A")

with col4:
    users = _load_users()
    approved = sum(1 for u in users.values() if u.get("approved"))
    st.metric("Subscribers", f"{approved}")

st.markdown("---")

# ── Tabs ──
tab1, tab2, tab3, tab4 = st.tabs(["📊 Trades", "👥 Users", "📡 Manual Signal", "⚙️ Config"])

# ── Tab 1: Trades ──
with tab1:
    st.subheader("Active Gold Trades")
    tm = st.session_state.get("trade_manager")
    if tm and tm.active_trades:
        for tid, trade in tm.active_trades.items():
            emoji = "🟢" if trade.direction == "Buy" else "🔴"
            st.markdown(
                f"{emoji} **{trade.direction} XAUUSD** @ {trade.entry:.2f} | "
                f"SL: {trade.sl_current:.2f} | TP: {trade.tp_hit_count}/10 | "
                f"Lots: {trade.lot_remaining}"
            )
    else:
        st.info("No active trades. Bot is scanning every 5 minutes during market hours.")

    st.subheader("Recent Closed Trades")
    if tm and tm.closed_trades:
        for t in tm.closed_trades[-10:]:
            emoji = "🟢" if "TP" in str(t.get("close_reason", "")) else "🔴"
            st.markdown(f"{emoji} XAUUSD — {t.get('close_reason')} | TPs: {t.get('tp_hit_count', 0)}/10")
    else:
        st.info("No closed trades yet.")

# ── Tab 2: Users ──
with tab2:
    st.subheader("Subscriber Management")
    users = _load_users()

    if users:
        total = len(users)
        approved_count = sum(1 for u in users.values() if u.get("approved"))
        pending_count = sum(1 for u in users.values() if u.get("state") == "pending_approval")
        rejected_count = sum(1 for u in users.values() if u.get("state") == "rejected")

        ucol1, ucol2, ucol3, ucol4 = st.columns(4)
        ucol1.metric("Total", total)
        ucol2.metric("Approved", approved_count)
        ucol3.metric("Pending", pending_count)
        ucol4.metric("Rejected", rejected_count)

        st.markdown("---")

        # Pending users
        if pending_count > 0:
            st.subheader("⏳ Pending Approval")
            for uid, u in users.items():
                if u.get("state") == "pending_approval":
                    st.markdown(
                        f"**{u.get('name', 'Unknown')}** "
                        f"(@{u.get('username', 'N/A')}) | "
                        f"Capital: {u.get('capital', 'N/A')} | "
                        f"Experience: {u.get('experience', 'N/A')}"
                    )
                    st.code(f"/approve {uid}", language="text")

        # All users table
        st.subheader("All Users")
        user_rows = []
        for uid, u in users.items():
            user_rows.append({
                "ID": uid,
                "Name": u.get("name", ""),
                "Username": u.get("username", ""),
                "Capital": u.get("capital", ""),
                "Experience": u.get("experience", ""),
                "Status": u.get("state", ""),
                "Approved": "✅" if u.get("approved") else "❌",
            })
        if user_rows:
            st.dataframe(user_rows, use_container_width=True)
    else:
        st.info("No users yet. Share your bot link for people to start onboarding!")

# ── Tab 3: Manual Signal ──
with tab3:
    st.subheader("Send Manual Gold Signal")
    st.markdown("This sends a signal to the Telegram channel and opens on MT5.")

    mcol1, mcol2 = st.columns(2)
    with mcol1:
        direction = st.selectbox("Direction", ["Buy", "Sell"])
        entry_price = st.number_input("Entry Price", value=2350.00, step=0.01, format="%.2f")
    with mcol2:
        sl_price = st.number_input("Stop Loss", value=2340.00, step=0.01, format="%.2f")
        lot_size = st.number_input("Lot Size", value=0.10, step=0.01, format="%.2f")

    if st.button("🚀 Send Signal", type="primary"):
        tm = st.session_state.get("trade_manager")
        notifier = st.session_state.get("notifier")
        if tm and notifier:
            trade = tm.open_trade("XAUUSD", direction, entry_price, sl_price, lot_size, source="manual")
            notifier.broadcast_signal(trade)
            st.success(f"Signal sent! Trade ID: {trade.id}")
        else:
            st.error("Bot not initialized yet.")

# ── Tab 4: Config ──
with tab4:
    st.subheader("Platform Configuration")

    st.markdown(f"**Platform:** {PLATFORM_NAME}")
    st.markdown(f"**Symbol:** {SYMBOL}")
    st.markdown(f"**Telegram Bot:** {'✅ Connected' if TELEGRAM_BOT_TOKEN else '❌ Not set'}")
    st.markdown(f"**Telegram Channel:** {'✅ ' + str(TELEGRAM_CHANNEL_ID) if TELEGRAM_CHANNEL_ID else '❌ Not set'}")
    st.markdown(f"**MetaAPI:** {'✅ Connected' if METAAPI_TOKEN else '❌ Not set'}")
    st.markdown(f"**Twelve Data:** {'✅ Connected' if TWELVE_DATA_KEY else '❌ Not set'}")

    rm = st.session_state.get("risk_manager")
    if rm:
        st.markdown("---")
        st.markdown("**Risk Settings:**")
        st.markdown(f"Risk per trade: {rm.risk_pct}%")
        st.markdown(f"Max concurrent trades: {rm.max_trades}")
        st.markdown(f"Max exposure: {rm.max_exposure_pct}%")

    st.markdown("---")
    st.markdown(f"**Bot started:** {st.session_state.get('bot_started_at', 'N/A')}")

# ── Auto-refresh every 30 seconds (without resetting session state) ──
import time as _time
_time.sleep(30)
st.rerun()
