"""
AlphaEdge Gold Signals — MT5 Executor

XAUUSD-only trade execution via MetaAPI.
Handles open, partial close, SL modification, full close.
"""
import logging
import time
import os
import requests
import urllib3
from config import METAAPI_TOKEN, METAAPI_ACCOUNT, SYMBOL, SYMBOL_SUFFIX

# Suppress SSL warnings — MetaAPI uses self-signed certs on some endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ["PYTHONHTTPSVERIFY"] = "0"

logger = logging.getLogger("alphaedge.mt5")

META_API_URL = "https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai"


class MT5Executor:
    """Executes gold trades on MT5 via MetaAPI."""

    def __init__(self, token=None, account_id=None):
        self.token = token or METAAPI_TOKEN
        self.account_id = account_id or METAAPI_ACCOUNT
        self.base = f"{META_API_URL}/users/current/accounts/{self.account_id}"
        self.headers = {
            "auth-token": self.token,
            "Content-Type": "application/json",
        }
        self._deployed = False
        self.mt5_symbol = SYMBOL + SYMBOL_SUFFIX  # e.g. "XAUUSD" or "XAUUSD.r"

    def ensure_deployed(self):
        """Make sure MetaAPI account is connected."""
        if self._deployed:
            return True
        try:
            resp = requests.get(
                f"https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
                f"/users/current/accounts/{self.account_id}",
                headers=self.headers,
                timeout=10, verify=False,
            )
            data = resp.json()

            if data.get("state") != "DEPLOYED":
                requests.post(
                    f"https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
                    f"/users/current/accounts/{self.account_id}/deploy",
                    headers=self.headers,
                    timeout=10,
                )
                logger.info("MetaAPI account deploying...")
                time.sleep(5)

            if data.get("connectionStatus") != "CONNECTED":
                for _ in range(12):
                    time.sleep(5)
                    resp2 = requests.get(
                        f"https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
                        f"/users/current/accounts/{self.account_id}",
                        headers=self.headers,
                        timeout=10,
                    )
                    if resp2.json().get("connectionStatus") == "CONNECTED":
                        break
                else:
                    logger.error("MT5 failed to connect within 60s")
                    return False

            self._deployed = True
            logger.info("MT5 connected — ready to trade gold")
            return True
        except Exception as e:
            logger.error(f"Deploy check failed: {e}")
            return False

    def get_account_info(self):
        """Get MT5 account balance, equity, margin."""
        try:
            resp = requests.get(
                f"{self.base}/account-information",
                headers=self.headers,
                timeout=10, verify=False,
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Account info error: {e}")
            return None

    def open_position(self, direction, lot, sl=None, tp=None, comment="AlphaEdge_Gold"):
        """Open a gold market order."""
        if not self.ensure_deployed():
            return None

        payload = {
            "actionType": "ORDER_TYPE_BUY" if direction == "Buy" else "ORDER_TYPE_SELL",
            "symbol": self.mt5_symbol,
            "volume": lot,
            "comment": comment,
        }
        if sl is not None:
            payload["stopLoss"] = sl
        if tp is not None:
            payload["takeProfit"] = tp

        try:
            resp = requests.post(
                f"{self.base}/trade",
                headers=self.headers,
                json=payload,
                timeout=15, verify=False,
            )
            data = resp.json()
            if data.get("numericCode") in [None, 10009]:
                ticket = data.get("positionId") or data.get("orderId")
                logger.info(f"Opened {direction} {lot} XAUUSD — ticket {ticket}")
                return {
                    "ticket": ticket,
                    "orderId": data.get("orderId"),
                    "stringCode": data.get("stringCode", "DONE"),
                }
            else:
                logger.error(f"Open failed: {data}")
                return None
        except Exception as e:
            logger.error(f"Open error: {e}")
            return None

    def close_position(self, ticket, lot=None):
        """Close gold position (full or partial)."""
        if not self.ensure_deployed():
            return False

        payload = {
            "actionType": "POSITION_CLOSE_ID",
            "positionId": str(ticket),
        }
        if lot is not None:
            payload["volume"] = lot

        try:
            resp = requests.post(
                f"{self.base}/trade",
                headers=self.headers,
                json=payload,
                timeout=15, verify=False,
            )
            data = resp.json()
            success = data.get("numericCode") in [None, 10009]
            if success:
                close_type = f"partial ({lot})" if lot else "full"
                logger.info(f"Closed {ticket} — {close_type}")
            else:
                logger.error(f"Close failed {ticket}: {data}")
            return success
        except Exception as e:
            logger.error(f"Close error: {e}")
            return False

    def modify_sl(self, ticket, new_sl):
        """Modify SL on gold position."""
        if not self.ensure_deployed():
            return False

        try:
            resp = requests.post(
                f"{self.base}/trade",
                headers=self.headers,
                json={
                    "actionType": "POSITION_MODIFY",
                    "positionId": str(ticket),
                    "stopLoss": new_sl,
                },
                timeout=15, verify=False,
            )
            data = resp.json()
            success = data.get("numericCode") in [None, 10009]
            if success:
                logger.info(f"SL modified {ticket} → {new_sl:.2f}")
            return success
        except Exception as e:
            logger.error(f"Modify SL error: {e}")
            return False

    def get_positions(self):
        """Get all open positions."""
        try:
            resp = requests.get(
                f"{self.base}/positions",
                headers=self.headers,
                timeout=10, verify=False,
            )
            return resp.json()
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []

    def get_gold_price(self):
        """Get current XAUUSD bid/ask from MT5."""
        try:
            resp = requests.get(
                f"{self.base}/symbols/{self.mt5_symbol}/current-price",
                headers=self.headers,
                timeout=10, verify=False,
            )
            data = resp.json()
            return {"bid": data.get("bid"), "ask": data.get("ask")}
        except Exception as e:
            logger.error(f"Get price error: {e}")
            return None


class TradeExecutionBridge:
    """Bridges TradeManager actions to MT5 for gold trades."""

    def __init__(self, mt5_executor):
        self.mt5 = mt5_executor
        self.trade_tickets = {}  # trade_id → mt5_ticket

    def execute_open(self, trade):
        """Open a gold trade on MT5."""
        result = self.mt5.open_position(
            direction=trade.direction,
            lot=trade.lot_total,
            sl=trade.sl_original,
            comment=f"AE_GOLD_{trade.id}",
        )
        if result:
            ticket = result["ticket"]
            self.trade_tickets[trade.id] = ticket
            trade.mt5_tickets.append(ticket)
            logger.info(f"MT5 gold trade opened — ticket {ticket}")
            return ticket
        return None

    def process_actions(self, actions):
        """Process TradeManager actions on MT5."""
        results = []

        for action in actions:
            trade = action.get("trade")
            trade_id = action.get("trade_id")
            act_type = action["action"]
            ticket = self.trade_tickets.get(trade_id)

            if not ticket:
                logger.warning(f"No MT5 ticket for trade {trade_id}")
                continue

            if act_type == "PARTIAL_CLOSE":
                success = self.mt5.close_position(ticket, lot=action["close_lot"])
                results.append({"action": "PARTIAL_CLOSE", "trade_id": trade_id, "success": success})

            elif act_type in ("MOVE_SL", "TRAIL_SL"):
                success = self.mt5.modify_sl(ticket, action["new_sl"])
                results.append({"action": act_type, "trade_id": trade_id, "success": success})

            elif act_type == "CLOSE_ALL":
                success = self.mt5.close_position(ticket)
                results.append({"action": "CLOSE_ALL", "trade_id": trade_id, "success": success})
                if success:
                    self.trade_tickets.pop(trade_id, None)

            elif act_type == "FULLY_CLOSED":
                self.trade_tickets.pop(trade_id, None)
                results.append({"action": "FULLY_CLOSED", "trade_id": trade_id, "success": True})

        return results
