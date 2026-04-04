"""
AlphaEdge Gold Signals — Signal Engine

XAUUSD-only signal generation using S/D zones + structure + confluence.

Gold-specific tuning:
- H4 zones for major S/D levels
- H1 structure for trend confirmation (BOS/CHoCH)
- M15 entry patterns (engulfing, pin bar, momentum shift)
- Gold session awareness (London open, NY open = best signals)
- RSI confluence filter
"""
import logging
import requests
import time
from datetime import datetime, timezone
from config import (
    TWELVE_DATA_KEY, SYMBOL, SYMBOL_PIP, SYMBOL_DEC,
    SYMBOLS, GOLD_KILLZONES, PLATFORM_NAME,
)

logger = logging.getLogger("alphaedge.signal_engine")


class GoldSignalEngine:
    """
    Generates XAUUSD trading signals using supply/demand + structure.

    Signal flow:
    1. Fetch H4, H1, M15, M5 candle data
    2. Detect S/D zones on H4
    3. Check H1 structure (BOS/CHoCH)
    4. Look for M15 entry patterns
    5. RSI confluence check
    6. Killzone session check
    7. Score ≥ 70 → fire signal
    """

    def __init__(self, on_signal=None):
        self.on_signal = on_signal
        self.last_signal_time = 0
        self.cooldown = 3600  # 1 hour cooldown between signals

    def scan(self):
        """
        Run a full scan on XAUUSD.
        Returns signal dict or None.
        """
        now = time.time()
        if now - self.last_signal_time < self.cooldown:
            return None

        try:
            signal = self._analyze_gold()
            if signal:
                self.last_signal_time = now
                if self.on_signal:
                    self.on_signal(signal)
                logger.info(
                    f"GOLD SIGNAL: {signal['direction']} @ {signal['entry']} "
                    f"SL={signal['sl']} Score={signal['score']} "
                    f"Session={signal.get('session', 'N/A')}"
                )
                return signal
        except Exception as e:
            logger.error(f"Gold scan error: {e}")

        return None

    def _analyze_gold(self):
        """Full multi-timeframe analysis for XAUUSD."""
        # Fetch candle data
        h4 = self._fetch_candles("4h", 100)
        h1 = self._fetch_candles("1h", 100)
        m15 = self._fetch_candles("15min", 50)
        m5 = self._fetch_candles("5min", 30)

        if not h4 or not h1 or not m15:
            return None

        # ── Gate 0: Session Check ──
        now_utc = datetime.now(timezone.utc)
        session = self._get_current_session(now_utc.hour)
        # We still generate signals outside killzones, but they score lower

        # ── Gate 1: H4 S/D Zone Detection ──
        h4_zones = self._detect_sd_zones(h4, pivot_len=4)
        if not h4_zones:
            return None

        current_price = m15[-1]["close"] if m15 else h1[-1]["close"]
        active_zone = self._find_active_zone(h4_zones, current_price)
        if not active_zone:
            return None

        # ── Gate 2: H1 Structure Confirmation ──
        h1_trend = self._detect_trend(h1)
        zone_type = active_zone["type"]

        if zone_type == "demand" and h1_trend != "bullish":
            return None
        if zone_type == "supply" and h1_trend != "bearish":
            return None

        # ── Gate 3: M15 Entry Pattern ──
        m15_pattern = self._detect_entry_pattern(m15, zone_type)
        if not m15_pattern:
            return None

        # ── Gate 4: M5 Confirmation (optional, boosts score) ──
        m5_confirm = False
        if m5:
            m5_pattern = self._detect_entry_pattern(m5, zone_type)
            m5_confirm = m5_pattern is not None

        # ── Gate 5: RSI Confluence ──
        rsi = self._compute_rsi(m15, 14)
        if zone_type == "demand" and rsi > 45:
            return None
        if zone_type == "supply" and rsi < 55:
            return None

        # ── Build Signal ──
        direction = "Buy" if zone_type == "demand" else "Sell"
        entry = current_price

        # SL: below zone low (demand) or above zone high (supply)
        # Gold gets 5 pip buffer ($0.50)
        if direction == "Buy":
            sl = active_zone["low"] - 5 * SYMBOL_PIP
        else:
            sl = active_zone["high"] + 5 * SYMBOL_PIP
        sl = round(sl, SYMBOL_DEC)

        # Validate minimum R:R
        sl_pips = abs(entry - sl) / SYMBOL_PIP
        if sl_pips <= 0 or sl_pips > 100:
            return None  # SL too tight or too wide

        # Minimum 1:1 R:R for TP1 (20 pips)
        if 20 / sl_pips < 1.0:
            return None

        # Score the signal
        score = self._score_signal(
            active_zone, h1_trend, m15_pattern, rsi, sl_pips,
            session, m5_confirm,
        )

        if score < 70:
            return None

        return {
            "symbol": SYMBOL,
            "direction": direction,
            "entry": round(entry, SYMBOL_DEC),
            "sl": sl,
            "lot": 0.01,  # Will be calculated by risk manager
            "score": score,
            "zone": active_zone,
            "h1_trend": h1_trend,
            "m15_pattern": m15_pattern,
            "m5_confirm": m5_confirm,
            "rsi": round(rsi, 1),
            "sl_pips": round(sl_pips, 1),
            "session": session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _fetch_candles(self, interval, count):
        """Fetch XAUUSD candles from Twelve Data."""
        if not TWELVE_DATA_KEY:
            return None

        try:
            resp = requests.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": "XAU/USD",
                    "interval": interval,
                    "outputsize": count,
                    "apikey": TWELVE_DATA_KEY,
                },
                timeout=15,
            )
            data = resp.json()
            values = data.get("values", [])
            if not values:
                return None

            candles = []
            for v in reversed(values):
                candles.append({
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                    "datetime": v["datetime"],
                })
            return candles
        except Exception as e:
            logger.error(f"Candle fetch error (XAU/USD {interval}): {e}")
            return None

    def _detect_sd_zones(self, candles, pivot_len=4):
        """Detect supply and demand zones from gold H4 candles."""
        zones = []
        if len(candles) < pivot_len * 2 + 1:
            return zones

        for i in range(pivot_len, len(candles) - pivot_len):
            is_high = all(
                candles[i]["high"] >= candles[i + d]["high"]
                for d in range(-pivot_len, pivot_len + 1) if d != 0
            )
            is_low = all(
                candles[i]["low"] <= candles[i + d]["low"]
                for d in range(-pivot_len, pivot_len + 1) if d != 0
            )

            if is_high:
                base = candles[i - 1]
                zones.append({
                    "type": "supply",
                    "high": candles[i]["high"],
                    "low": min(base["open"], base["close"]),
                    "time": candles[i]["datetime"],
                    "strength": self._zone_strength(candles, i, "supply"),
                })

            if is_low:
                base = candles[i - 1]
                zones.append({
                    "type": "demand",
                    "high": max(base["open"], base["close"]),
                    "low": candles[i]["low"],
                    "time": candles[i]["datetime"],
                    "strength": self._zone_strength(candles, i, "demand"),
                })

        return zones

    def _zone_strength(self, candles, idx, zone_type):
        """Rate zone strength — gold-tuned (bigger departure = stronger zone)."""
        if idx + 3 >= len(candles):
            return 50

        departure = 0
        for j in range(1, min(4, len(candles) - idx)):
            if zone_type == "demand":
                departure += candles[idx + j]["close"] - candles[idx + j]["open"]
            else:
                departure += candles[idx + j]["open"] - candles[idx + j]["close"]

        avg_range = sum(c["high"] - c["low"] for c in candles[max(0, idx - 10):idx + 1]) / 11
        if avg_range > 0:
            strength = min(100, max(0, int((departure / avg_range) * 33 + 50)))
        else:
            strength = 50
        return strength

    def _find_active_zone(self, zones, current_price):
        """Find nearest active zone for XAUUSD."""
        # Gold proximity: 30 pips = $3.00 move
        proximity = 30 * SYMBOL_PIP

        best = None
        best_dist = float("inf")

        for z in zones:
            if z["strength"] < 60:
                continue

            if z["type"] == "demand":
                dist = current_price - z["high"]
                if -proximity <= dist <= proximity * 2:
                    if abs(dist) < best_dist:
                        best = z
                        best_dist = abs(dist)
            elif z["type"] == "supply":
                dist = z["low"] - current_price
                if -proximity <= dist <= proximity * 2:
                    if abs(dist) < best_dist:
                        best = z
                        best_dist = abs(dist)

        return best

    def _detect_trend(self, candles):
        """Detect H1 trend using swing structure."""
        if len(candles) < 20:
            return "neutral"

        recent = candles[-20:]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        hh = highs[-1] > highs[-5] > highs[-10]
        hl = lows[-1] > lows[-5] > lows[-10]
        lh = highs[-1] < highs[-5] < highs[-10]
        ll = lows[-1] < lows[-5] < lows[-10]

        if hh and hl:
            return "bullish"
        elif lh and ll:
            return "bearish"
        return "neutral"

    def _detect_entry_pattern(self, candles, zone_type):
        """Detect entry patterns on M15/M5."""
        if len(candles) < 3:
            return None

        last = candles[-1]
        prev = candles[-2]

        body_last = abs(last["close"] - last["open"])
        body_prev = abs(prev["close"] - prev["open"])

        if zone_type == "demand":
            # Bullish engulfing
            if (last["close"] > last["open"] and
                prev["close"] < prev["open"] and
                body_last > body_prev * 1.2 and
                last["close"] > prev["open"]):
                return "bullish_engulfing"

            # Bullish pin bar
            lower_wick = min(last["open"], last["close"]) - last["low"]
            upper_wick = last["high"] - max(last["open"], last["close"])
            if body_last > 0 and lower_wick > body_last * 2 and upper_wick < body_last * 0.5:
                return "bullish_pin"

            # Momentum shift
            if last["close"] > last["open"] and prev["close"] < prev["open"]:
                return "momentum_shift"

        if zone_type == "supply":
            # Bearish engulfing
            if (last["close"] < last["open"] and
                prev["close"] > prev["open"] and
                body_last > body_prev * 1.2 and
                last["close"] < prev["open"]):
                return "bearish_engulfing"

            # Bearish pin bar
            upper_wick = last["high"] - max(last["open"], last["close"])
            lower_wick = min(last["open"], last["close"]) - last["low"]
            if body_last > 0 and upper_wick > body_last * 2 and lower_wick < body_last * 0.5:
                return "bearish_pin"

            # Momentum shift
            if last["close"] < last["open"] and prev["close"] > prev["open"]:
                return "momentum_shift"

        return None

    def _compute_rsi(self, candles, period=14):
        """RSI calculation."""
        if len(candles) < period + 1:
            return 50

        closes = [c["close"] for c in candles]
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(0, delta))
            losses.append(max(0, -delta))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _get_current_session(self, hour_utc):
        """Determine which gold killzone we're in."""
        for name, times in GOLD_KILLZONES.items():
            if times["start"] <= hour_utc < times["end"]:
                return name
        return "off_session"

    def _score_signal(self, zone, trend, pattern, rsi, sl_pips, session, m5_confirm):
        """Score signal 0-100 with gold-specific weighting."""
        score = 0

        # Zone strength (0-30)
        score += min(30, zone["strength"] * 0.3)

        # Pattern quality (0-25)
        pattern_scores = {
            "bullish_engulfing": 25,
            "bearish_engulfing": 25,
            "bullish_pin": 20,
            "bearish_pin": 20,
            "momentum_shift": 12,
        }
        score += pattern_scores.get(pattern, 5)

        # RSI confluence (0-15)
        if zone["type"] == "demand":
            rsi_score = max(0, (45 - rsi)) * 0.5
        else:
            rsi_score = max(0, (rsi - 55)) * 0.5
        score += min(15, rsi_score)

        # Tight SL bonus (0-10) — gold specific (10-30 pips ideal)
        if 10 <= sl_pips <= 20:
            score += 10
        elif sl_pips <= 30:
            score += 7
        elif sl_pips <= 50:
            score += 3

        # Session bonus (0-15) — gold moves best in London/NY
        session_scores = {
            "london_open": 15,
            "ny_open": 15,
            "ny_session": 10,
            "off_session": 0,
        }
        score += session_scores.get(session, 0)

        # M5 confirmation bonus (0-5)
        if m5_confirm:
            score += 5

        # Trend alignment (already filtered, free 5 points)
        score += 5

        return min(100, int(score))
