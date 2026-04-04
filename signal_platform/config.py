"""
AlphaEdge Gold Signals — Configuration
XAUUSD only. Focused. Profitable.
"""
import os
from pathlib import Path

# Load .env file if it exists
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

# ── Platform Identity ────────────────────────────────────
PLATFORM_NAME = "AlphaEdge Gold Signals"
PLATFORM_TAG = "alphaedge_gold"

# ── Telegram Bot ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")  # e.g. "@alphaedge_gold"

# ── MetaAPI (MT5 Connection) ──────────────────────────────
METAAPI_TOKEN = os.environ.get("METAAPI_TOKEN", "")
METAAPI_ACCOUNT = os.environ.get("METAAPI_ACCOUNT", "")

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ── Twelve Data (for price feeds) ─────────────────────────
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

# ── Gold (XAUUSD) Configuration ──────────────────────────
# This platform ONLY trades XAUUSD
SYMBOL = "XAUUSD"
SYMBOL_PIP = 0.1       # Gold pip = $0.10
SYMBOL_DEC = 2          # 2 decimal places
SYMBOL_SUFFIX = ".r"    # Ryan's broker uses XAUUSD.r

# Kept for backward compatibility with modules that reference SYMBOLS dict
SYMBOLS = {
    "XAUUSD": {"pip": SYMBOL_PIP, "dec": SYMBOL_DEC, "suffix": SYMBOL_SUFFIX},
}

# ── Gold-Specific TP Levels ──────────────────────────────
# 10-level take profit system (in pips, where 1 pip = $0.10 for gold)
# Gold moves big — these levels are tuned for gold volatility
#
# TP1-TP4: Quick scalp profits (20 pips each = $2.00 move each)
# TP5-TP6: Medium swing (30-40 pips = $3.00-$4.00)
# TP7-TP8: Extended move (50 pips each = $5.00)
# TP9-TP10: Full runner (60 pips each = $6.00)
#
# Total if all 10 TPs hit: 370 pips = $37.00 move
TP_LEVELS_PIPS = [20, 20, 20, 20, 30, 40, 50, 50, 60, 60]

# Lot distribution per TP level (percentage of total position)
# Equal 10% each → smooth position reduction
TP_LOT_PCT = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]

# SL behavior
SL_MOVE_TO_BE_AFTER_TP = 1   # Move SL to breakeven after TP1 hit
SL_TRAIL_AFTER_TP = 4        # Start trailing SL by structure after TP4 hit

# ── Gold Session Times (UTC) ─────────────────────────────
# Gold is most active during London + NY overlap
GOLD_KILLZONES = {
    "london_open":  {"start": 7, "end": 10},    # 07:00-10:00 UTC
    "ny_open":      {"start": 12, "end": 15},   # 12:00-15:00 UTC (London/NY overlap)
    "ny_session":   {"start": 15, "end": 20},   # 15:00-20:00 UTC
}

# ── Risk Management ──────────────────────────────────────
DEFAULT_RISK_PCT = 1.0       # 1% risk per trade
MAX_CONCURRENT_TRADES = 3    # Max 3 gold trades at once (correlated!)
MAX_EXPOSURE_PCT = 3.0       # Max 3% total exposure (gold is volatile)

# ── Gold Pip Value ────────────────────────────────────────
# For XAUUSD: 1 standard lot (100 oz), 1 pip ($0.10) = $10
# So: pip_value_per_lot = $10 per 0.1 price movement per lot
GOLD_PIP_VALUE_PER_LOT = 10

# ── Admin Configuration ──────────────────────────────────
ADMIN_TELEGRAM_IDS = [5045841960]  # Ryan's Telegram user ID

# ── FP Markets Referral ──────────────────────────────────
FP_MARKETS_LINK = os.environ.get(
    "FP_MARKETS_LINK",
    "https://portal.fpmarkets.com/register?fpm-affiliate-utm-source=IB&fpm-affiliate-agt=66209"
)
FP_MARKETS_CODE = "M4-66209"

# ── Group Invite Link ────────────────────────────────────
# Set this after creating your Telegram group
GROUP_INVITE_LINK = os.environ.get("GROUP_INVITE_LINK", "")
