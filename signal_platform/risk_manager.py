"""
AlphaEdge Gold Signals — Risk Manager

XAUUSD-only risk calculation.
Gold pip = $0.10, pip value per standard lot = $10.
"""
import logging
from config import (
    SYMBOL_PIP, GOLD_PIP_VALUE_PER_LOT,
    DEFAULT_RISK_PCT, MAX_CONCURRENT_TRADES, MAX_EXPOSURE_PCT,
)

logger = logging.getLogger("alphaedge.risk")


class RiskManager:
    """
    Gold-focused risk management.
    Calculates lot size based on SL distance and account risk.
    """

    def __init__(self, balance=10000, risk_pct=None, max_trades=None, max_exposure_pct=None):
        self.balance = balance
        self.risk_pct = risk_pct or DEFAULT_RISK_PCT
        self.max_trades = max_trades or MAX_CONCURRENT_TRADES
        self.max_exposure_pct = max_exposure_pct or MAX_EXPOSURE_PCT
        self.current_trades = 0
        self.current_risk = 0.0

    def update_balance(self, balance):
        self.balance = balance

    def can_open_trade(self):
        if self.current_trades >= self.max_trades:
            logger.warning(f"Max gold trades reached ({self.max_trades})")
            return False

        current_risk_pct = (self.current_risk / self.balance * 100) if self.balance > 0 else 100
        if current_risk_pct >= self.max_exposure_pct:
            logger.warning(f"Max gold exposure reached ({current_risk_pct:.1f}%)")
            return False

        return True

    def calculate_lot_size(self, entry, sl):
        """
        Calculate lot size for XAUUSD.

        Gold: 1 standard lot = 100 oz
        1 pip ($0.10 move) × 1 lot = $10
        So: lot = risk_amount / (sl_pips × $10)
        """
        sl_pips = abs(entry - sl) / SYMBOL_PIP

        if sl_pips <= 0:
            logger.error(f"Invalid SL distance: {sl_pips} pips")
            return 0.01

        risk_amount = self.balance * (self.risk_pct / 100)
        lot = risk_amount / (sl_pips * GOLD_PIP_VALUE_PER_LOT)

        # Round down to nearest 0.01
        lot = max(0.01, round(int(lot * 100) / 100, 2))

        # Cap at 5.0 lots for safety
        lot = min(lot, 5.0)

        logger.info(
            f"Gold lot calc: Risk USD {risk_amount:.2f} | "
            f"SL {sl_pips:.0f} pips | Lot {lot}"
        )
        return lot

    def register_trade(self, lot, sl_pips):
        """Register a new gold trade."""
        trade_risk = lot * sl_pips * GOLD_PIP_VALUE_PER_LOT
        self.current_risk += trade_risk
        self.current_trades += 1

    def unregister_trade(self, lot, sl_pips):
        """Remove a closed gold trade."""
        trade_risk = lot * sl_pips * GOLD_PIP_VALUE_PER_LOT
        self.current_risk = max(0, self.current_risk - trade_risk)
        self.current_trades = max(0, self.current_trades - 1)

    def get_status(self):
        return {
            "balance": self.balance,
            "risk_pct": self.risk_pct,
            "current_trades": self.current_trades,
            "max_trades": self.max_trades,
            "current_risk_usd": round(self.current_risk, 2),
            "current_risk_pct": round(self.current_risk / self.balance * 100, 2) if self.balance > 0 else 0,
            "max_exposure_pct": self.max_exposure_pct,
            "can_trade": self.can_open_trade(),
        }
