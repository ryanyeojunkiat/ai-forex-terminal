"""
AlphaEdge Gold Signals — Trade Manager

XAUUSD-only trade management with 10-level TP system.
- Opens position with total lot size
- Partially closes 10% at each TP level
- Moves SL to breakeven after TP1
- Trails SL by structure after TP4
"""
import uuid
from datetime import datetime, timezone
from config import (
    TP_LEVELS_PIPS, TP_LOT_PCT, SL_MOVE_TO_BE_AFTER_TP,
    SL_TRAIL_AFTER_TP, SYMBOL, SYMBOL_PIP, SYMBOL_DEC,
    PLATFORM_NAME,
)


class Trade:
    """Represents a single XAUUSD trade with 10 TP levels."""

    def __init__(self, direction, entry, sl, lot, source="auto"):
        self.id = str(uuid.uuid4())[:8]
        self.symbol = SYMBOL  # Always XAUUSD
        self.direction = direction
        self.entry = entry
        self.sl_original = sl
        self.sl_current = sl
        self.lot_total = lot
        self.lot_remaining = lot
        self.source = source
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status = "PENDING"

        # Build 10 TP levels
        self.tp_levels = []
        cumulative_pips = 0
        for i, pips in enumerate(TP_LEVELS_PIPS):
            cumulative_pips += pips
            if direction == "Buy":
                tp_price = entry + cumulative_pips * SYMBOL_PIP
            else:
                tp_price = entry - cumulative_pips * SYMBOL_PIP
            lot_pct = TP_LOT_PCT[i] / 100.0
            self.tp_levels.append({
                "level": i + 1,
                "pips": cumulative_pips,
                "price": round(tp_price, SYMBOL_DEC),
                "lot_pct": lot_pct,
                "lot_size": round(lot * lot_pct, 2),
                "hit": False,
                "hit_at": None,
            })

        self.tp_hit_count = 0
        self.pnl_pips = 0
        self.pnl_usd = 0
        self.mt5_tickets = []
        self.closed_at = None
        self.close_reason = None

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "sl_original": self.sl_original,
            "sl_current": self.sl_current,
            "lot_total": self.lot_total,
            "lot_remaining": self.lot_remaining,
            "source": self.source,
            "status": self.status,
            "tp_levels": self.tp_levels,
            "tp_hit_count": self.tp_hit_count,
            "pnl_pips": self.pnl_pips,
            "pnl_usd": self.pnl_usd,
            "created_at": self.created_at,
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
        }

    def check_price(self, current_price):
        """
        Check gold price against TP levels and SL.
        Returns list of actions.
        """
        actions = []
        if self.status != "ACTIVE":
            return actions

        # ── Check SL hit ──
        sl_hit = False
        if self.direction == "Buy" and current_price <= self.sl_current:
            sl_hit = True
        elif self.direction == "Sell" and current_price >= self.sl_current:
            sl_hit = True

        if sl_hit:
            actions.append({
                "action": "CLOSE_ALL",
                "reason": "SL_HIT",
                "price": self.sl_current,
                "detail": f"SL hit at {self.sl_current:.2f} — closing {self.lot_remaining} lots"
            })
            self.status = "CLOSED"
            self.close_reason = "SL"
            self.closed_at = datetime.now(timezone.utc).isoformat()
            return actions

        # ── Check TP levels (in order) ──
        for tp in self.tp_levels:
            if tp["hit"]:
                continue

            tp_hit = False
            if self.direction == "Buy" and current_price >= tp["price"]:
                tp_hit = True
            elif self.direction == "Sell" and current_price <= tp["price"]:
                tp_hit = True

            if tp_hit:
                tp["hit"] = True
                tp["hit_at"] = datetime.now(timezone.utc).isoformat()
                self.tp_hit_count += 1
                close_lot = tp["lot_size"]
                self.lot_remaining = round(self.lot_remaining - close_lot, 2)

                actions.append({
                    "action": "PARTIAL_CLOSE",
                    "reason": f"TP{tp['level']}_HIT",
                    "price": tp["price"],
                    "close_lot": close_lot,
                    "remaining_lot": self.lot_remaining,
                    "pips": tp["pips"],
                    "detail": (
                        f"TP{tp['level']} hit at {tp['price']:.2f} (+{tp['pips']} pips) "
                        f"— closed {close_lot} lots, {self.lot_remaining} remaining"
                    ),
                })

                # ── SL → Breakeven after TP1 ──
                if self.tp_hit_count == SL_MOVE_TO_BE_AFTER_TP:
                    buffer = SYMBOL_PIP * 2  # $0.20 buffer
                    if self.direction == "Buy":
                        new_sl = self.entry + buffer
                    else:
                        new_sl = self.entry - buffer
                    self.sl_current = round(new_sl, SYMBOL_DEC)
                    actions.append({
                        "action": "MOVE_SL",
                        "reason": "BREAKEVEN",
                        "new_sl": self.sl_current,
                        "detail": f"SL moved to breakeven: {self.sl_current:.2f}"
                    })

                # ── Trail SL after TP4 ──
                if self.tp_hit_count >= SL_TRAIL_AFTER_TP:
                    prev_tp_idx = self.tp_hit_count - 2
                    if prev_tp_idx >= 0:
                        trail_price = self.tp_levels[prev_tp_idx]["price"]
                        should_trail = (
                            (self.direction == "Buy" and trail_price > self.sl_current) or
                            (self.direction == "Sell" and trail_price < self.sl_current)
                        )
                        if should_trail:
                            self.sl_current = trail_price
                            actions.append({
                                "action": "TRAIL_SL",
                                "reason": f"TRAIL_TP{self.tp_hit_count}",
                                "new_sl": self.sl_current,
                                "detail": f"SL trailed to {self.sl_current:.2f} (locked TP{prev_tp_idx + 1} profit)"
                            })

                # ── All TPs hit ──
                if self.tp_hit_count >= len(self.tp_levels) or self.lot_remaining <= 0:
                    self.status = "CLOSED"
                    self.close_reason = f"TP{self.tp_hit_count}"
                    self.closed_at = datetime.now(timezone.utc).isoformat()
                    actions.append({
                        "action": "FULLY_CLOSED",
                        "reason": "ALL_TP_HIT",
                        "detail": f"All 10 TPs hit — trade fully closed! 🏆"
                    })

        return actions

    def format_signal_message(self):
        """Format gold signal for Telegram."""
        emoji = "🟢" if self.direction == "Buy" else "🔴"
        dir_text = "BUY" if self.direction == "Buy" else "SELL"

        lines = [
            f"{'━' * 28}",
            f"🥇 {emoji} <b>{dir_text} XAUUSD</b> (Gold)",
            f"{'━' * 28}",
            f"",
            f"📍 Entry: <code>{self.entry:.2f}</code>",
            f"🛑 SL: <code>{self.sl_original:.2f}</code>",
            f"",
        ]

        for tp in self.tp_levels:
            lines.append(f"🎯 TP{tp['level']}: <code>{tp['price']:.2f}</code> (+{tp['pips']} pips)")

        sl_pips = abs(self.entry - self.sl_original) / SYMBOL_PIP
        total_pips = self.tp_levels[-1]["pips"]
        rr = total_pips / sl_pips if sl_pips > 0 else 0

        lines.extend([
            f"",
            f"📊 SL: {sl_pips:.0f} pips | Max TP: +{total_pips} pips",
            f"📈 Risk:Reward = 1:{rr:.1f}",
            f"",
            f"⚡ After TP1 → SL moves to <b>BREAKEVEN</b>",
            f"📐 After TP4 → SL <b>TRAILS</b> by structure",
            f"",
            f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
            f"🥇 {PLATFORM_NAME} | {'Auto' if self.source == 'auto' else 'Manual'} Signal",
        ])

        return "\n".join(lines)

    def format_tp_hit_message(self, tp_level, price):
        """Format TP hit notification."""
        tp = self.tp_levels[tp_level - 1]
        remaining_tps = len(self.tp_levels) - self.tp_hit_count

        return (
            f"🎯 <b>TP{tp_level} HIT!</b> — XAUUSD 🥇\n"
            f"{'━' * 28}\n"
            f"Price: <code>{price:.2f}</code> (+{tp['pips']} pips)\n"
            f"Remaining TPs: {remaining_tps}\n"
            f"SL: <code>{self.sl_current:.2f}</code>"
            f"{' (BREAKEVEN)' if self.tp_hit_count >= SL_MOVE_TO_BE_AFTER_TP else ''}\n"
            f"{'━' * 28}\n"
            f"🥇 {PLATFORM_NAME}"
        )

    def format_close_message(self):
        """Format trade close notification."""
        if self.close_reason == "SL" and self.tp_hit_count == 0:
            emoji = "🔴"
            result = "LOSS"
        elif self.close_reason == "SL" and self.tp_hit_count > 0:
            emoji = "🟡"
            result = f"PARTIAL WIN (TP{self.tp_hit_count} hit before SL)"
        else:
            emoji = "🟢"
            result = f"WIN — {self.tp_hit_count} TPs hit! 🏆"

        return (
            f"{emoji} <b>TRADE CLOSED</b> — XAUUSD 🥇\n"
            f"{'━' * 28}\n"
            f"Result: <b>{result}</b>\n"
            f"TPs Hit: {self.tp_hit_count}/{len(self.tp_levels)}\n"
            f"Close Reason: {self.close_reason}\n"
            f"{'━' * 28}\n"
            f"🥇 {PLATFORM_NAME}"
        )


class TradeManager:
    """Manages active gold trades."""

    def __init__(self):
        self.active_trades = {}
        self.closed_trades = []

    def open_trade(self, symbol, direction, entry, sl, lot, source="auto"):
        """Create a new gold trade. Symbol param kept for API compatibility."""
        trade = Trade(direction, entry, sl, lot, source)
        trade.status = "ACTIVE"
        self.active_trades[trade.id] = trade
        return trade

    def close_trade(self, trade_id, reason="manual"):
        """Manually close a trade."""
        trade = self.active_trades.get(trade_id)
        if trade:
            trade.status = "CLOSED"
            trade.close_reason = reason
            trade.closed_at = datetime.now(timezone.utc).isoformat()
            self.closed_trades.append(trade.to_dict())
            del self.active_trades[trade_id]
            return trade
        return None

    def check_all_prices(self, prices):
        """
        Check gold price against all active trades.
        prices: dict {symbol: price} or just pass {"XAUUSD": price}
        """
        all_actions = []
        closed_ids = []

        gold_price = prices.get(SYMBOL) or prices.get("XAUUSD")
        if gold_price is None:
            return all_actions

        for trade_id, trade in self.active_trades.items():
            actions = trade.check_price(gold_price)
            for a in actions:
                a["trade_id"] = trade_id
                a["symbol"] = SYMBOL
                a["trade"] = trade
            all_actions.extend(actions)
            if trade.status == "CLOSED":
                self.closed_trades.append(trade.to_dict())
                closed_ids.append(trade_id)

        for tid in closed_ids:
            del self.active_trades[tid]

        return all_actions

    def get_active_summary(self):
        """Get summary of all active gold trades."""
        return [
            {
                "id": t.id,
                "symbol": SYMBOL,
                "direction": t.direction,
                "entry": t.entry,
                "sl": t.sl_current,
                "tp_hit": t.tp_hit_count,
                "lot_remaining": t.lot_remaining,
                "status": t.status,
            }
            for t in self.active_trades.values()
        ]
