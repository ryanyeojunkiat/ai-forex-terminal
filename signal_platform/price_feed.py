"""
AlphaEdge Gold Signals — Price Feed

XAUUSD-only price monitoring.
Primary: MetaAPI (direct MT5 bid/ask)
Fallback: Twelve Data REST
"""
import logging
import time
import threading
import requests
from datetime import datetime, timezone
from config import (
    TWELVE_DATA_KEY, SYMBOL, SYMBOL_PIP, SYMBOL_DEC, SYMBOL_SUFFIX,
    METAAPI_TOKEN, METAAPI_ACCOUNT,
)

logger = logging.getLogger("alphaedge.price_feed")


class GoldPriceFeed:
    """
    Real-time XAUUSD price feed.
    Polls every 2 seconds and fires callback with gold price.
    """

    def __init__(self, on_tick=None, interval=2.0):
        self.on_tick = on_tick
        self.interval = interval
        self.price = None  # Latest {bid, ask, mid, time}
        self._running = False
        self._thread = None
        self._source = "metaapi"

        self._meta_base = (
            f"https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai"
            f"/users/current/accounts/{METAAPI_ACCOUNT}"
        )
        self._meta_headers = {
            "auth-token": METAAPI_TOKEN,
            "Content-Type": "application/json",
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"Gold price feed started — {self.interval}s interval")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Gold price feed stopped")

    def get_price(self):
        """Get latest gold mid price."""
        return self.price.get("mid") if self.price else None

    def get_bid_ask(self):
        """Get latest bid/ask."""
        return self.price if self.price else None

    def _poll_loop(self):
        fail_count = 0

        while self._running:
            try:
                price_data = None

                if self._source == "metaapi" and METAAPI_TOKEN:
                    price_data = self._fetch_metaapi()
                    if price_data:
                        fail_count = 0
                    else:
                        fail_count += 1
                        if fail_count >= 3:
                            logger.warning("MetaAPI failed 3x, switching to Twelve Data")
                            self._source = "twelvedata"
                            fail_count = 0
                elif TWELVE_DATA_KEY:
                    price_data = self._fetch_twelvedata()

                if price_data:
                    price_data["time"] = datetime.now(timezone.utc).isoformat()
                    self.price = price_data

                    if self.on_tick:
                        self.on_tick({SYMBOL: price_data["mid"]})

            except Exception as e:
                logger.error(f"Price feed error: {e}")

            time.sleep(self.interval)

    def _fetch_metaapi(self):
        """Fetch XAUUSD price from MetaAPI."""
        mt5_sym = SYMBOL + SYMBOL_SUFFIX
        try:
            resp = requests.get(
                f"{self._meta_base}/symbols/{mt5_sym}/current-price",
                headers=self._meta_headers,
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                bid = data.get("bid")
                ask = data.get("ask")
                if bid and ask:
                    return {
                        "bid": bid,
                        "ask": ask,
                        "mid": round((bid + ask) / 2, SYMBOL_DEC),
                    }
        except Exception:
            pass
        return None

    def _fetch_twelvedata(self):
        """Fetch XAUUSD price from Twelve Data."""
        try:
            resp = requests.get(
                "https://api.twelvedata.com/price",
                params={
                    "symbol": "XAU/USD",
                    "apikey": TWELVE_DATA_KEY,
                },
                timeout=10,
            )
            data = resp.json()
            if "price" in data:
                mid = float(data["price"])
                spread = SYMBOL_PIP * 0.5  # Estimated $0.05 spread
                return {
                    "bid": round(mid - spread, SYMBOL_DEC),
                    "ask": round(mid + spread, SYMBOL_DEC),
                    "mid": round(mid, SYMBOL_DEC),
                }
        except Exception as e:
            logger.error(f"Twelve Data fetch error: {e}")
        return None
